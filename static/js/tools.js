/**
 * TONY AI Assistant - Stage 5 Tools & Windows Automation Client Controller
 * Manages the Tools modal/drawer, tools catalog, activity telemetry log,
 * and high-risk action confirmation banner with natural click controls.
 */

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const openToolsBtn = document.getElementById("openToolsBtn");
    const closeToolsBtn = document.getElementById("closeToolsBtn");
    const toolsModalOverlay = document.getElementById("toolsModalOverlay");
    const toolsCardsContainer = document.getElementById("toolsCardsContainer");
    const toolsActivityContainer = document.getElementById("toolsActivityContainer");
    const hudToolsCountVal = document.getElementById("hudToolsCountVal");
    const modalToolsCountBadge = document.getElementById("modalToolsCountBadge");

    // Confirmation Banner Elements
    const confirmationBanner = document.getElementById("confirmationBanner");
    const confirmationMessage = document.getElementById("confirmationMessage");
    const confirmationActionId = document.getElementById("confirmationActionId");
    const confirmationTimer = document.getElementById("confirmationTimer");
    const btnConfirmAction = document.getElementById("btnConfirmAction");
    const btnCancelAction = document.getElementById("btnCancelAction");

    let currentPendingAction = null;
    let countdownInterval = null;

    // Open / Close Modal
    function openToolsModal() {
        if (!toolsModalOverlay) return;
        toolsModalOverlay.classList.add("active");
        fetchToolsCatalog();
        fetchToolsActivity();
    }

    function closeToolsModal() {
        if (!toolsModalOverlay) return;
        toolsModalOverlay.classList.remove("active");
    }

    if (openToolsBtn) openToolsBtn.addEventListener("click", openToolsModal);
    if (closeToolsBtn) closeToolsBtn.addEventListener("click", closeToolsModal);

    if (toolsModalOverlay) {
        toolsModalOverlay.addEventListener("click", (e) => {
            if (e.target === toolsModalOverlay) {
                closeToolsModal();
            }
        });
    }

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && toolsModalOverlay && toolsModalOverlay.classList.contains("active")) {
            closeToolsModal();
        }
    });

    // Tab Navigation inside Tools Modal
    document.querySelectorAll(".tools-tab-btn").forEach(tabBtn => {
        tabBtn.addEventListener("click", () => {
            const targetTab = tabBtn.getAttribute("data-tab");
            document.querySelectorAll(".tools-tab-btn").forEach(b => b.classList.remove("active"));
            tabBtn.classList.add("active");

            const catalogContent = document.getElementById("tabToolCatalog");
            const activityContent = document.getElementById("tabToolActivity");

            if (targetTab === "catalog") {
                if (catalogContent) catalogContent.style.display = "block";
                if (activityContent) activityContent.style.display = "none";
                fetchToolsCatalog();
            } else {
                if (catalogContent) catalogContent.style.display = "none";
                if (activityContent) activityContent.style.display = "block";
                fetchToolsActivity();
            }
        });
    });

    // Escape HTML Helper
    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    // Format Risk Badge
    function renderRiskBadge(risk) {
        const r = (risk || "low").toLowerCase();
        let cls = "risk-low";
        if (r === "medium") cls = "risk-medium";
        if (r === "high") cls = "risk-high";
        if (r === "critical") cls = "risk-critical";
        return `<span class="tool-risk-badge ${cls}">${r.toUpperCase()} RISK</span>`;
    }

    // Fetch and display tool catalog
    async function fetchToolsCatalog() {
        if (!toolsCardsContainer) return;
        toolsCardsContainer.innerHTML = '<div class="tools-loading">Querying registered tool catalog...</div>';

        try {
            const res = await fetch("/api/tools");
            if (!res.ok) throw new Error("Could not retrieve tool catalog");
            const data = await res.json();

            if (!data.tools || data.tools.length === 0) {
                toolsCardsContainer.innerHTML = '<div class="tools-empty">No tools currently registered.</div>';
                return;
            }

            if (hudToolsCountVal) hudToolsCountVal.textContent = data.count;
            if (modalToolsCountBadge) modalToolsCountBadge.textContent = `${data.count} TOOLS`;

            let html = "";
            data.tools.forEach(tool => {
                const examplesHtml = (tool.examples || [])
                    .map(ex => `<span class="tool-example-tag">"${escapeHtml(ex)}"</span>`)
                    .join(" ");

                const paramsHtml = Object.keys(tool.parameters || {})
                    .map(k => `<span class="tool-param-pill"><code>${escapeHtml(k)}</code>: ${escapeHtml(tool.parameters[k].type)}</span>`)
                    .join(" ") || '<span class="text-muted">None</span>';

                html += `
                    <div class="tool-card">
                        <div class="tool-card-header">
                            <div class="tool-name-category">
                                <span class="tool-name">${escapeHtml(tool.name)}</span>
                                <span class="tool-category-badge">${escapeHtml(tool.category)}</span>
                            </div>
                            ${renderRiskBadge(tool.risk_level)}
                        </div>
                        <div class="tool-description">${escapeHtml(tool.description)}</div>
                        <div class="tool-params-section">
                            <span class="tool-section-label">Parameters:</span> ${paramsHtml}
                        </div>
                        ${examplesHtml ? `<div class="tool-examples-section"><span class="tool-section-label">Commands:</span> ${examplesHtml}</div>` : ""}
                    </div>
                `;
            });

            toolsCardsContainer.innerHTML = html;
        } catch (err) {
            toolsCardsContainer.innerHTML = `<div class="tools-error">Failed to load tools: ${escapeHtml(err.message)}</div>`;
        }
    }

    // Fetch and display tool activity log
    async function fetchToolsActivity() {
        if (!toolsActivityContainer) return;
        toolsActivityContainer.innerHTML = '<div class="tools-loading">Loading telemetry activity log...</div>';

        try {
            const res = await fetch("/api/tools/stats");
            if (!res.ok) throw new Error("Could not retrieve tool activity");
            const data = await res.json();

            const activity = (data.stats && data.stats.recent_activity) || [];
            if (activity.length === 0) {
                toolsActivityContainer.innerHTML = '<div class="tools-empty">No tool actions executed yet in this session.</div>';
                return;
            }

            let html = '<div class="activity-timeline">';
            activity.slice().reverse().forEach(item => {
                const statusCls = item.status === "SUCCESS" ? "status-success" : (item.status === "CONFIRMATION_REQUIRED" ? "status-pending" : "status-failed");
                html += `
                    <div class="activity-row">
                        <span class="activity-time">[${escapeHtml(item.timestamp)}]</span>
                        <span class="activity-tool">${escapeHtml(item.tool)}</span>
                        <span class="activity-status ${statusCls}">${escapeHtml(item.status)}</span>
                        <span class="activity-msg">${escapeHtml(item.message)}</span>
                    </div>
                `;
            });
            html += '</div>';

            toolsActivityContainer.innerHTML = html;
        } catch (err) {
            toolsActivityContainer.innerHTML = `<div class="tools-error">Failed to load activity log: ${escapeHtml(err.message)}</div>`;
        }
    }

    // Check for Active Pending Confirmation Actions
    async function checkPendingConfirmations() {
        try {
            const res = await fetch("/api/tools/pending");
            if (!res.ok) return;
            const data = await res.json();

            if (data.pending && data.pending.length > 0) {
                const latest = data.pending[data.pending.length - 1];
                showConfirmationBanner(latest);
            } else {
                hideConfirmationBanner();
            }
        } catch (err) {
            console.debug("Failed to check pending actions:", err);
        }
    }

    function showConfirmationBanner(action) {
        if (!confirmationBanner) return;
        currentPendingAction = action;

        if (confirmationMessage) {
            confirmationMessage.textContent = action.description || `Execute ${action.tool_name}`;
        }
        if (confirmationActionId) {
            confirmationActionId.textContent = action.id;
        }

        confirmationBanner.style.display = "flex";

        // Countdown timer
        clearInterval(countdownInterval);
        const expiresAt = action.expires_at ? action.expires_at * 1000 : Date.now() + 60000;

        function updateTimer() {
            const remaining = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
            if (confirmationTimer) confirmationTimer.textContent = `${remaining}s`;
            if (remaining <= 0) {
                clearInterval(countdownInterval);
                hideConfirmationBanner();
            }
        }
        updateTimer();
        countdownInterval = setInterval(updateTimer, 1000);
    }

    function hideConfirmationBanner() {
        if (!confirmationBanner) return;
        confirmationBanner.style.display = "none";
        currentPendingAction = null;
        clearInterval(countdownInterval);
    }

    // Execute Confirmation Button
    if (btnConfirmAction) {
        btnConfirmAction.addEventListener("click", async () => {
            if (!currentPendingAction) return;
            const actionId = currentPendingAction.id;
            btnConfirmAction.disabled = true;

            try {
                const res = await fetch("/api/tools/confirm", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ confirmation_id: actionId })
                });
                const data = await res.json();
                hideConfirmationBanner();

                // Append assistant notice in chat
                window.dispatchEvent(new CustomEvent("tonyExternalMessage", {
                    detail: {
                        role: "assistant",
                        text: data.success ? `Confirmed. ${data.message}` : `Action failed: ${data.message}`,
                        model: "tool_confirmation"
                    }
                }));

                fetchToolsActivity();
            } catch (err) {
                alert(`Confirmation error: ${err.message}`);
            } finally {
                btnConfirmAction.disabled = false;
            }
        });
    }

    // Cancel Action Button
    if (btnCancelAction) {
        btnCancelAction.addEventListener("click", async () => {
            if (!currentPendingAction) return;
            const actionId = currentPendingAction.id;
            btnCancelAction.disabled = true;

            try {
                await fetch("/api/tools/cancel", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ confirmation_id: actionId })
                });
                hideConfirmationBanner();

                window.dispatchEvent(new CustomEvent("tonyExternalMessage", {
                    detail: {
                        role: "assistant",
                        text: "Action cancelled. No modifications were made.",
                        model: "tool_confirmation"
                    }
                }));

                fetchToolsActivity();
            } catch (err) {
                alert(`Cancellation error: ${err.message}`);
            } finally {
                btnCancelAction.disabled = false;
            }
        });
    }

    // Re-check pending actions when a message is completed
    window.addEventListener("tonyMessageCompleted", () => {
        checkPendingConfirmations();
        fetchToolsActivity();
    });

    // Check on startup
    checkPendingConfirmations();
});
