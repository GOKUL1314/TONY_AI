/**
 * TONY AI Stage 10: Advanced Agentic Task Management & Live Progress Client
 * Provides DAG visualization, real-time SSE progress streaming,
 * and controls for pause, resume, cancel, retry, and confirmation.
 */

document.addEventListener("DOMContentLoaded", () => {
    const activeTasksList = document.getElementById("activeTasksList");

    /**
     * Render an Agent Task Card with DAG steps, progress bar, and controls.
     */
    window.tonyRenderAgentCard = function(task, container) {
        if (!task || !container) return;

        let card = document.getElementById(`agentCard_${task.task_id}`);
        if (!card) {
            card = document.createElement("div");
            card.id = `agentCard_${task.task_id}`;
            container.appendChild(card);
        }

        const plan = task.plan || {};
        const steps = plan.steps || [];
        const progress = plan.progress_percent !== undefined ? plan.progress_percent : 0;
        const status = (task.status || "queued").toLowerCase();

        // Status badge style
        let badgeClass = "running";
        if (status === "completed") badgeClass = "completed";
        else if (status === "failed") badgeClass = "failed";
        else if (status === "waiting_confirmation") badgeClass = "waiting";
        else if (status === "paused") badgeClass = "paused";
        else if (status === "cancelled") badgeClass = "failed";

        // Build Steps HTML
        const stepsHtml = steps.map((s, idx) => {
            let icon = "○";
            let sClass = s.status || "pending";
            if (sClass === "completed") icon = "✓";
            else if (sClass === "running") icon = "●";
            else if (sClass === "waiting_confirmation") icon = "⚠️";
            else if (sClass === "failed") icon = "✗";
            else if (sClass === "paused") icon = "⏸";
            else if (sClass === "blocked") icon = "⊘";

            let depText = "";
            if (s.dependencies && s.dependencies.length > 0) {
                depText = `<span class="step-dep">depends on: ${escapeHtml(s.dependencies.join(", "))}</span>`;
            }

            let obsText = "";
            if (s.observation && s.observation.detected_entities) {
                const ents = Object.entries(s.observation.detected_entities)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(" | ");
                if (ents) {
                    obsText = `<div class="step-entities">Detected: ${escapeHtml(ents)}</div>`;
                }
            }

            return `
                <div class="agent-step-item ${sClass}">
                    <div class="step-left">
                        <span class="step-status-icon">${icon}</span>
                        <div class="step-details">
                            <span class="step-name">${escapeHtml(s.description || s.step_id)}</span>
                            ${depText}
                            ${obsText}
                            ${s.error ? `<div class="step-error-msg">${escapeHtml(s.error)}</div>` : ""}
                        </div>
                    </div>
                    <span class="step-type-pill">${escapeHtml(s.action_type || "")}</span>
                </div>
            `;
        }).join("");

        // Control Buttons
        let controlsHtml = "";
        if (status === "waiting_confirmation") {
            controlsHtml = `
                <div class="agent-controls-bar confirmation-alert">
                    <span class="alert-icon">⚠️</span>
                    <span class="alert-msg">Human Authorization Required</span>
                    <div class="agent-btn-row">
                        <button class="btn-agent-act confirm-btn" data-act="confirm" data-task-id="${escapeHtml(task.task_id)}">Authorize</button>
                        <button class="btn-agent-act cancel-btn" data-act="cancel" data-task-id="${escapeHtml(task.task_id)}">Reject</button>
                    </div>
                </div>
            `;
        } else if (status === "running") {
            controlsHtml = `
                <div class="agent-controls-bar">
                    <button class="btn-agent-act pause-btn" data-act="pause" data-task-id="${escapeHtml(task.task_id)}">Pause</button>
                    <button class="btn-agent-act cancel-btn" data-act="cancel" data-task-id="${escapeHtml(task.task_id)}">Cancel</button>
                </div>
            `;
        } else if (status === "paused") {
            controlsHtml = `
                <div class="agent-controls-bar">
                    <button class="btn-agent-act resume-btn" data-act="resume" data-task-id="${escapeHtml(task.task_id)}">Resume</button>
                    <button class="btn-agent-act cancel-btn" data-act="cancel" data-task-id="${escapeHtml(task.task_id)}">Cancel</button>
                </div>
            `;
        } else if (status === "failed") {
            controlsHtml = `
                <div class="agent-controls-bar">
                    <button class="btn-agent-act retry-btn" data-act="retry" data-task-id="${escapeHtml(task.task_id)}">Retry</button>
                </div>
            `;
        }

        card.className = `agent-task-card ${status}`;
        card.innerHTML = `
            <div class="agent-card-header">
                <div class="agent-card-title">
                    <span class="agent-icon">⚡</span>
                    <span class="agent-goal">${escapeHtml(task.user_goal || "Agent Task")}</span>
                </div>
                <span class="agent-status-badge ${badgeClass}">${escapeHtml(status.toUpperCase())}</span>
            </div>
            <div class="agent-progress-track">
                <div class="agent-progress-fill" style="width: ${progress}%;"></div>
            </div>
            <div class="agent-progress-label">Progress: ${progress}%</div>
            <div class="agent-steps-list">
                ${stepsHtml}
            </div>
            ${controlsHtml}
        `;

        // Wire event listeners on control buttons
        card.querySelectorAll(".btn-agent-act").forEach(btn => {
            btn.addEventListener("click", async () => {
                const act = btn.dataset.act;
                const tid = btn.dataset.taskId;
                btn.disabled = true;
                try {
                    const res = await fetch(`/api/agent/tasks/${encodeURIComponent(tid)}/${act}`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" }
                    });
                    const updated = await res.json();
                    if (updated && updated.task_id) {
                        window.tonyRenderAgentCard(updated, container);
                    }
                } catch (e) {
                    console.error(`Agent ${act} action failed:`, e);
                } finally {
                    btn.disabled = false;
                }
            });
        });

        // Listen for live SSE events if task is active
        if (status === "running" && !card.dataset.sseActive) {
            card.dataset.sseActive = "true";
            const evtSource = new EventSource(`/api/agent/tasks/${encodeURIComponent(task.task_id)}/events`);
            evtSource.onmessage = (e) => {
                try {
                    const evt = JSON.parse(e.data);
                    if (evt.progress !== undefined) {
                        const fill = card.querySelector(".agent-progress-fill");
                        const lbl = card.querySelector(".agent-progress-label");
                        if (fill) fill.style.width = `${evt.progress}%`;
                        if (lbl) lbl.textContent = `Progress: ${evt.progress}%`;
                    }
                    if (evt.status && ["completed", "failed", "cancelled"].includes(evt.status.toLowerCase())) {
                        evtSource.close();
                        card.dataset.sseActive = "";
                        // Fetch final state
                        fetch(`/api/agent/tasks/${encodeURIComponent(task.task_id)}`)
                            .then(r => r.json())
                            .then(d => { if (d.task_id) window.tonyRenderAgentCard(d, container); });
                    }
                } catch (err) {
                    console.warn("SSE parse error", err);
                }
            };
            evtSource.onerror = () => {
                evtSource.close();
                card.dataset.sseActive = "";
            };
        }
    };

    function escapeHtml(text) {
        if (!text) return "";
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }
});
