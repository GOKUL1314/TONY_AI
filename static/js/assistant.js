/**
 * TONY AI Assistant - Stage 8 Intelligence & Orchestration Client
 * Manages Central Orb states, multi-step task cards, activity panel,
 * confirmation gates, and real-time execution feedback.
 */

document.addEventListener("DOMContentLoaded", () => {
    // Orb DOM Elements
    const tonyOrb = document.getElementById("tonyOrb");
    const orbStateLabel = document.getElementById("orbStateLabel");

    // Activity Drawer DOM Elements
    const activityDrawer = document.getElementById("activityDrawer");
    const closeActivityDrawer = document.getElementById("closeActivityDrawer");
    const activeTasksList = document.getElementById("activeTasksList");
    const recentMediaGallery = document.getElementById("recentMediaGallery");

    // Quick Actions
    const quickButtons = document.querySelectorAll(".quick-act-btn");
    const messageInput = document.getElementById("messageInput");
    const chatForm = document.getElementById("chatForm");

    const VALID_ORB_STATES = [
        "idle",
        "listening",
        "thinking",
        "planning",
        "working",
        "speaking",
        "waiting_confirmation",
        "error"
    ];

    /**
     * Update the Central TONY Orb's visual state and telemetry label.
     */
    window.tonySetOrbState = function(state) {
        if (!tonyOrb) return;
        const normalized = (state || "idle").toLowerCase().replace(/\s+/g, "_");
        const activeState = VALID_ORB_STATES.includes(normalized) ? normalized : "idle";

        // Remove previous state classes
        VALID_ORB_STATES.forEach(s => tonyOrb.classList.remove(s));
        tonyOrb.classList.add(activeState);

        if (orbStateLabel) {
            orbStateLabel.textContent = activeState.replace(/_/g, " ").toUpperCase();
        }
    };

    // Initialize Orb to idle
    window.tonySetOrbState("idle");

    /**
     * Render a structured multi-step Task Plan Card in chat.
     */
    window.tonyRenderTaskCard = function(plan, container) {
        if (!plan || !container) return;

        const card = document.createElement("div");
        card.className = `task-plan-card ${plan.status.toLowerCase()}`;
        card.id = `taskCard_${plan.task_id}`;

        const isWaiting = plan.status === "WAITING_CONFIRMATION";
        const statusBadgeClass = isWaiting ? "waiting" : (plan.status === "COMPLETED" ? "completed" : (plan.status === "FAILED" ? "failed" : "running"));

        let stepsHtml = "";
        if (plan.steps && plan.steps.length > 0) {
            stepsHtml = plan.steps.map((step, idx) => {
                let icon = "○";
                let statusClass = "pending";
                if (step.status === "COMPLETED") {
                    icon = "✓";
                    statusClass = "completed";
                } else if (step.status === "RUNNING") {
                    icon = "●";
                    statusClass = "running";
                } else if (step.status === "WAITING_CONFIRMATION") {
                    icon = "⚠️";
                    statusClass = "waiting";
                } else if (step.status === "FAILED") {
                    icon = "✗";
                    statusClass = "failed";
                }

                return `
                    <div class="task-step-row ${statusClass}">
                        <span class="step-icon">${icon}</span>
                        <div class="step-info">
                            <span class="step-desc">${escapeHtml(step.description)}</span>
                            ${step.error ? `<span class="step-err">${escapeHtml(step.error)}</span>` : ""}
                        </div>
                    </div>
                `;
            }).join("");
        }

        let confirmationHtml = "";
        if (isWaiting) {
            confirmationHtml = `
                <div class="task-card-confirmation">
                    <div class="conf-alert-text">⚠️ Authorization Required to proceed with high-risk action.</div>
                    <div class="conf-btn-group">
                        <button type="button" class="btn-task-confirm" data-task-id="${escapeHtml(plan.task_id)}">CONFIRM</button>
                        <button type="button" class="btn-task-cancel" data-task-id="${escapeHtml(plan.task_id)}">CANCEL</button>
                    </div>
                </div>
            `;
        }

        card.innerHTML = `
            <div class="task-card-header">
                <div class="task-card-title">
                    <span class="task-pulse-dot"></span>
                    <span>TASK PLAN // ${escapeHtml(plan.task_id)}</span>
                </div>
                <span class="task-status-badge ${statusBadgeClass}">${escapeHtml(plan.status)}</span>
            </div>
            <div class="task-steps-container">
                ${stepsHtml}
            </div>
            ${confirmationHtml}
        `;

        // Wire up confirmation buttons
        const confirmBtn = card.querySelector(".btn-task-confirm");
        const cancelBtn = card.querySelector(".btn-task-cancel");

        if (confirmBtn) {
            confirmBtn.addEventListener("click", async () => {
                confirmBtn.disabled = true;
                if (cancelBtn) cancelBtn.disabled = true;
                window.tonySetOrbState("working");
                try {
                    const resp = await fetch(`/api/assistant/tasks/${encodeURIComponent(plan.task_id)}/confirm`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" }
                    });
                    const result = await resp.json();
                    if (result.steps) {
                        card.replaceWith(window.tonyCreateTaskCardElement(result));
                    }
                } catch (e) {
                    console.error("Confirmation error:", e);
                } finally {
                    window.tonySetOrbState("idle");
                }
            });
        }

        if (cancelBtn) {
            cancelBtn.addEventListener("click", async () => {
                cancelBtn.disabled = true;
                if (confirmBtn) confirmBtn.disabled = true;
                try {
                    const resp = await fetch(`/api/assistant/tasks/${encodeURIComponent(plan.task_id)}/cancel`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" }
                    });
                    const result = await resp.json();
                    card.replaceWith(window.tonyCreateTaskCardElement(result));
                } catch (e) {
                    console.error("Cancellation error:", e);
                }
            });
        }

        container.appendChild(card);
    };

    window.tonyCreateTaskCardElement = function(plan) {
        const dummy = document.createElement("div");
        window.tonyRenderTaskCard(plan, dummy);
        return dummy.firstElementChild;
    };

    // Quick Action Buttons
    quickButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const action = btn.dataset.action;
            if (action === "image") {
                if (messageInput) {
                    messageInput.value = "Create an image of ";
                    messageInput.focus();
                }
            } else if (action === "video") {
                if (messageInput) {
                    messageInput.value = "Create a video of ";
                    messageInput.focus();
                }
            } else if (action === "active-video") {
                if (messageInput) {
                    messageInput.value = "Turn that image into a cinematic video";
                    if (chatForm) chatForm.dispatchEvent(new Event("submit"));
                }
            } else if (action === "project") {
                if (messageInput) {
                    messageInput.value = "Open my TONY AI project folder";
                    if (chatForm) chatForm.dispatchEvent(new Event("submit"));
                }
            } else if (action === "memory") {
                const memBtn = document.getElementById("openMemoryBtn");
                if (memBtn) memBtn.click();
            } else if (action === "activity") {
                toggleActivityDrawer();
            }
        });
    });

    const openActivityBtn = document.getElementById("openActivityBtn");
    const activityDrawerOverlay = document.getElementById("activityDrawerOverlay");

    if (openActivityBtn) {
        openActivityBtn.addEventListener("click", () => toggleActivityDrawer());
    }

    // Activity Drawer Toggle
    function toggleActivityDrawer() {
        if (!activityDrawerOverlay) return;
        const isVisible = activityDrawerOverlay.style.display === "flex";
        if (isVisible) {
            activityDrawerOverlay.style.display = "none";
        } else {
            activityDrawerOverlay.style.display = "flex";
            loadActivityData();
        }
    }

    if (closeActivityDrawer) {
        closeActivityDrawer.addEventListener("click", () => {
            if (activityDrawerOverlay) activityDrawerOverlay.style.display = "none";
        });
    }

    if (activityDrawerOverlay) {
        activityDrawerOverlay.addEventListener("click", (e) => {
            if (e.target === activityDrawerOverlay) {
                activityDrawerOverlay.style.display = "none";
            }
        });
    }

    async function loadActivityData() {
        // Load active tasks
        if (activeTasksList) {
            try {
                const resp = await fetch("/api/assistant/tasks/active");
                const data = await resp.json();
                if (data.active_tasks && data.active_tasks.length > 0) {
                    activeTasksList.innerHTML = data.active_tasks.map(t => `
                        <div class="active-task-item">
                            <div class="task-item-head">
                                <span class="task-id">${escapeHtml(t.task_id)}</span>
                                <span class="task-status">${escapeHtml(t.status)}</span>
                            </div>
                            <div class="task-req">"${escapeHtml(t.original_request)}"</div>
                        </div>
                    `).join("");
                } else {
                    activeTasksList.innerHTML = `<div class="empty-state">No active background tasks</div>`;
                }
            } catch (e) {
                activeTasksList.innerHTML = `<div class="empty-state">Could not load active tasks</div>`;
            }
        }

        // Load recent media thumbnails
        if (recentMediaGallery) {
            try {
                const imgResp = await fetch("/api/images?limit=4");
                const imgData = await imgResp.json();
                const images = imgData.images || [];

                if (images.length > 0) {
                    recentMediaGallery.innerHTML = images.map(img => `
                        <div class="mini-media-thumb" title="${escapeHtml(img.prompt)}">
                            <img src="${escapeHtml(img.url)}" alt="${escapeHtml(img.prompt)}">
                        </div>
                    `).join("");
                } else {
                    recentMediaGallery.innerHTML = `<div class="empty-state">No generated media recorded yet</div>`;
                }
            } catch {
                recentMediaGallery.innerHTML = `<div class="empty-state">Media gallery idle</div>`;
            }
        }
    }

    function escapeHtml(text) {
        if (!text) return "";
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }
});
