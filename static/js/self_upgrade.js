/**
 * TONY AI Controlled Self-Upgrade & Intelligence Diagnostic Studio.
 * Handles telemetry inspection, upgrade planning, test execution, and rollbacks.
 */
document.addEventListener("DOMContentLoaded", () => {
    const modalOverlay = document.getElementById("selfUpgradeModalOverlay");
    const openBtn = document.getElementById("openSelfUpgradeBtn");
    const closeBtn = document.getElementById("closeSelfUpgradeModalBtn");

    const btnRunDiagnostic = document.getElementById("btnRunDiagnostic");
    const btnCreateUpgradePlan = document.getElementById("btnCreateUpgradePlan");
    const btnApplyApprovedUpgrade = document.getElementById("btnApplyApprovedUpgrade");
    const btnRunTests = document.getElementById("btnRunTests");
    const btnRollbackUpgrade = document.getElementById("btnRollbackUpgrade");
    const btnClearUpgradeLog = document.getElementById("btnClearUpgradeLog");

    const terminalLog = document.getElementById("upgradeTerminalLog");
    const valSysHealth = document.getElementById("valSysHealth");
    const valIntelHealth = document.getElementById("valIntelHealth");
    const valProviderHealth = document.getElementById("valProviderHealth");
    const valTestStatus = document.getElementById("valTestStatus");

    const valPendingStatus = document.getElementById("valPendingStatus");
    const valPendingId = document.getElementById("valPendingId");
    const valPendingReason = document.getElementById("valPendingReason");
    const valRiskLevel = document.getElementById("valRiskLevel");
    const valTestsAffected = document.getElementById("valTestsAffected");
    const valChangedFiles = document.getElementById("valChangedFiles");
    const historyContainer = document.getElementById("upgradeHistoryContainer");

    let currentUpgradeId = null;

    function logTerminal(msg) {
        if (!terminalLog) return;
        const timeStr = new Date().toLocaleTimeString();
        terminalLog.textContent += `\n[${timeStr}] ${msg}`;
        terminalLog.scrollTop = terminalLog.scrollHeight;
    }

    // Open / Close modal
    if (openBtn && modalOverlay) {
        openBtn.addEventListener("click", () => {
            modalOverlay.style.display = "flex";
            refreshStatus();
        });
    }

    if (closeBtn && modalOverlay) {
        closeBtn.addEventListener("click", () => {
            modalOverlay.style.display = "none";
        });
    }

    if (btnClearUpgradeLog && terminalLog) {
        btnClearUpgradeLog.addEventListener("click", () => {
            terminalLog.textContent = "Ready.";
        });
    }

    async function refreshStatus() {
        try {
            const res = await fetch("/api/self-upgrade/status");
            if (!res.ok) return;
            const data = await res.json();

            if (valSysHealth) valSysHealth.textContent = data.healthy ? "ONLINE" : "DEGRADED";
            if (valIntelHealth) {
                const intHealthy = data.subsystems && data.subsystems.intelligence && data.subsystems.intelligence.healthy;
                valIntelHealth.textContent = intHealthy ? "ACTIVE" : "DEGRADED";
            }
            if (valProviderHealth) {
                const aiHealthy = data.subsystems && data.subsystems.ai_provider && data.subsystems.ai_provider.healthy;
                valProviderHealth.textContent = aiHealthy ? "HEALTHY" : "STANDBY";
            }

            renderHistory(data.last_upgrade ? [data.last_upgrade] : []);
        } catch (e) {
            console.error("Failed to load self-upgrade status:", e);
        }
    }

    function renderHistory(records) {
        if (!historyContainer) return;
        if (!records || records.length === 0) {
            historyContainer.innerHTML = '<div class="empty-state">No upgrade history recorded yet.</div>';
            return;
        }

        historyContainer.innerHTML = records.map(rec => `
            <div class="upgrade-history-item">
                <div class="item-header">
                    <strong>${rec.upgrade_id}</strong>
                    <span class="status-tag ${rec.status.toLowerCase()}">${rec.status}</span>
                </div>
                <div class="item-reason">${rec.reason}</div>
                <div class="item-meta">Files: ${rec.files_changed ? rec.files_changed.join(", ") : "None"} | Risk: ${rec.risk_level || "LOW"}</div>
            </div>
        `).join("");
    }

    // 1. RUN DIAGNOSTIC
    if (btnRunDiagnostic) {
        btnRunDiagnostic.addEventListener("click", async () => {
            logTerminal("Running full subsystem diagnostic evaluation...");
            try {
                const res = await fetch("/api/self-upgrade/diagnose");
                const data = await res.json();
                if (res.ok && data.diagnostic) {
                    logTerminal(`Diagnostic complete. Healthy: ${data.diagnostic.healthy}`);
                    for (const [sub, info] of Object.entries(data.diagnostic.subsystems || {})) {
                        logTerminal(` • ${sub}: ${info.healthy ? "HEALTHY" : "DEGRADED"}`);
                    }
                    if (data.diagnostic.recommendations && data.diagnostic.recommendations.length > 0) {
                        logTerminal("Recommendations:");
                        data.diagnostic.recommendations.forEach(r => logTerminal(`   - ${r}`));
                    }
                    refreshStatus();
                } else {
                    logTerminal(`Diagnostic error: ${data.error || "Unknown error"}`);
                }
            } catch (e) {
                logTerminal(`Diagnostic network error: ${e.message}`);
            }
        });
    }

    // 2. CREATE UPGRADE PLAN
    if (btnCreateUpgradePlan) {
        btnCreateUpgradePlan.addEventListener("click", async () => {
            logTerminal("Formulating proposed upgrade plan...");
            try {
                const res = await fetch("/api/self-upgrade/plan", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        reason: "Strengthen capability validation and response evaluation",
                        files: ["intelligence/evaluator.py", "intelligence/pipeline.py"]
                    })
                });
                const data = await res.json();
                if (res.ok && data.plan) {
                    currentUpgradeId = data.plan.upgrade_id;
                    if (valPendingStatus) valPendingStatus.textContent = "WAITING CONFIRMATION";
                    if (valPendingId) valPendingId.textContent = currentUpgradeId;
                    if (valPendingReason) valPendingReason.textContent = data.plan.reason;
                    if (valRiskLevel) valRiskLevel.textContent = data.plan.risk_level;
                    if (valTestsAffected) valTestsAffected.textContent = data.plan.tests_affected;
                    if (valChangedFiles) valChangedFiles.textContent = data.plan.files_changed.join(", ");

                    logTerminal(`Plan formulated: ${currentUpgradeId}`);
                    logTerminal(`Reason: ${data.plan.reason}`);
                    logTerminal(`Risk: ${data.plan.risk_level} | Tests Affected: ${data.plan.tests_affected}`);
                    logTerminal("Confirmation required. Click 'APPLY APPROVED UPGRADE' to execute.");
                } else {
                    logTerminal(`Plan error: ${data.error || "Could not generate plan"}`);
                }
            } catch (e) {
                logTerminal(`Planning network error: ${e.message}`);
            }
        });
    }

    // 3. APPLY APPROVED UPGRADE
    if (btnApplyApprovedUpgrade) {
        btnApplyApprovedUpgrade.addEventListener("click", async () => {
            if (!currentUpgradeId) {
                logTerminal("No active upgrade plan selected. Click 'CREATE UPGRADE PLAN' first.");
                return;
            }
            logTerminal(`Applying upgrade ${currentUpgradeId}... Checkpoint backup initiated.`);
            try {
                const res = await fetch("/api/self-upgrade/apply", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ upgrade_id: currentUpgradeId })
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    logTerminal(`SUCCESS: ${data.message}`);
                    if (valPendingStatus) valPendingStatus.textContent = "COMPLETED";
                    if (valTestStatus && data.test_result) {
                        valTestStatus.textContent = `${data.test_result.passed} PASS`;
                    }
                    refreshStatus();
                } else {
                    logTerminal(`UPGRADE FAILED: ${data.message || data.error}`);
                    if (valPendingStatus) valPendingStatus.textContent = "FAILED / ROLLED BACK";
                    refreshStatus();
                }
            } catch (e) {
                logTerminal(`Apply network error: ${e.message}`);
            }
        });
    }

    // 4. RUN TESTS
    if (btnRunTests) {
        btnRunTests.addEventListener("click", async () => {
            logTerminal("Running test verification suite via python unittest...");
            try {
                const res = await fetch("/api/self-upgrade/test", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({})
                });
                const data = await res.json();
                if (res.ok && data.result) {
                    logTerminal(`Tests execution finished in ${data.result.duration_seconds}s.`);
                    logTerminal(`Total: ${data.result.total} | Passed: ${data.result.passed} | Failed: ${data.result.failed} | Errors: ${data.result.errors} | Skipped: ${data.result.skipped}`);
                    if (valTestStatus) {
                        valTestStatus.textContent = `${data.result.passed} PASS`;
                    }
                } else {
                    logTerminal(`Test execution failed: ${data.error || "Unknown"}`);
                }
            } catch (e) {
                logTerminal(`Test runner network error: ${e.message}`);
            }
        });
    }

    // 5. ROLLBACK
    if (btnRollbackUpgrade) {
        btnRollbackUpgrade.addEventListener("click", async () => {
            if (!currentUpgradeId) {
                logTerminal("No active upgrade plan ID to roll back.");
                return;
            }
            logTerminal(`Rolling back upgrade ${currentUpgradeId} to backup checkpoint...`);
            try {
                const res = await fetch("/api/self-upgrade/rollback", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ upgrade_id: currentUpgradeId })
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    logTerminal(`ROLLBACK SUCCESS: ${data.message}`);
                    if (valPendingStatus) valPendingStatus.textContent = "ROLLED BACK";
                    refreshStatus();
                } else {
                    logTerminal(`Rollback error: ${data.error || "Failed to rollback"}`);
                }
            } catch (e) {
                logTerminal(`Rollback network error: ${e.message}`);
            }
        });
    }
});
