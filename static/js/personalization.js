/**
 * TONY AI - Personalization & Proactive Intelligence Client Controller (Stage 12)
 * Manages user profile, preferences, scheduled reminders, routines,
 * proactive toggles, grounded briefings, and delivered notifications.
 */

class TonyPersonalizationStudio {
    constructor() {
        // Modal elements
        this.overlay = document.getElementById("personalizationModalOverlay");
        this.openBtn = document.getElementById("openPersonalizationBtn");
        this.closeBtn = document.getElementById("closePersonalizationModalBtn");
        this.statusBanner = document.getElementById("personalizationStatusBanner");
        this.statusText = document.getElementById("personalizationStatusText");
        this.badgeCount = document.getElementById("personalizationNotificationCount");

        // Tabs
        this.tabBtns = document.querySelectorAll(".personalization-tabs .tab-btn");
        this.tabContents = document.querySelectorAll(".personalization-tab-content");

        // Profile elements
        this.profUserName = document.getElementById("profUserName");
        this.profPreferredAddress = document.getElementById("profPreferredAddress");
        this.profRole = document.getElementById("profRole");
        this.profTimezone = document.getElementById("profTimezone");
        this.profCommStyle = document.getElementById("profCommStyle");
        this.profTone = document.getElementById("profTone");
        this.profVerbosity = document.getElementById("profVerbosity");
        this.profWakeWord = document.getElementById("profWakeWord");
        this.btnSaveProfile = document.getElementById("btnSaveProfile");
        this.btnReset = document.getElementById("btnResetPersonalization");

        // Preferences elements
        this.prefKey = document.getElementById("prefKey");
        this.prefVal = document.getElementById("prefVal");
        this.prefCat = document.getElementById("prefCat");
        this.btnSetPref = document.getElementById("btnSetPreference");
        this.prefsListContainer = document.getElementById("preferencesListContainer");

        // Reminders elements
        this.remTitle = document.getElementById("newRemTitle");
        this.remDueTime = document.getElementById("newRemDueTime");
        this.remRecurrence = document.getElementById("newRemRecurrence");
        this.btnScheduleRem = document.getElementById("btnScheduleReminder");
        this.btnRefreshReminders = document.getElementById("btnRefreshReminders");
        this.remindersListContainer = document.getElementById("remindersListContainer");

        // Routines elements
        this.routineBtns = document.querySelectorAll(".btn-run-routine");
        this.routineResultBox = document.getElementById("routineResultBox");
        this.routineResultText = document.getElementById("routineResultText");

        // Proactive & Briefings elements
        this.proactiveToggle = document.getElementById("proactiveToggleSwitch");
        this.proactiveStatusText = document.getElementById("proactiveStatusText");
        this.dispQuietHours = document.getElementById("dispQuietHours");
        this.dispMaxActions = document.getElementById("dispMaxActions");
        this.btnGenMorning = document.getElementById("btnGenMorningBriefing");
        this.btnGenEvening = document.getElementById("btnGenEveningSummary");
        this.briefingShowcase = document.getElementById("briefingResultShowcase");
        this.briefingTitle = document.getElementById("briefingResultTitle");
        this.briefingBody = document.getElementById("briefingResultBody");
        this.btnSpeakBriefing = document.getElementById("btnSpeakBriefing");

        // Notifications elements
        this.notificationsListContainer = document.getElementById("notificationsListContainer");
        this.btnDismissAllNotifs = document.getElementById("btnDismissAllNotifications");

        this.currentBriefingText = "";

        this.init();
    }

    init() {
        if (this.openBtn) {
            this.openBtn.addEventListener("click", () => this.open());
        }
        if (this.closeBtn) {
            this.closeBtn.addEventListener("click", () => this.close());
        }
        if (this.overlay) {
            this.overlay.addEventListener("click", (e) => {
                if (e.target === this.overlay) this.close();
            });
        }

        // Tab Switching
        this.tabBtns.forEach(btn => {
            btn.addEventListener("click", () => {
                const target = btn.getAttribute("data-tab");
                this.switchTab(target);
            });
        });

        // Profile Events
        if (this.btnSaveProfile) {
            this.btnSaveProfile.addEventListener("click", () => this.saveProfile());
        }
        if (this.btnReset) {
            this.btnReset.addEventListener("click", () => this.resetPersonalization());
        }

        // Preference Events
        if (this.btnSetPref) {
            this.btnSetPref.addEventListener("click", () => this.savePreference());
        }

        // Reminder Events
        if (this.btnScheduleRem) {
            this.btnScheduleRem.addEventListener("click", () => this.createReminder());
        }
        if (this.btnRefreshReminders) {
            this.btnRefreshReminders.addEventListener("click", () => this.loadReminders());
        }

        // Routine Events
        this.routineBtns.forEach(btn => {
            btn.addEventListener("click", () => {
                const rName = btn.getAttribute("data-routine");
                this.runRoutine(rName);
            });
        });

        // Proactive Events
        if (this.proactiveToggle) {
            this.proactiveToggle.addEventListener("change", (e) => {
                this.toggleProactive(e.target.checked);
            });
        }
        if (this.btnGenMorning) {
            this.btnGenMorning.addEventListener("click", () => this.generateBriefing("morning"));
        }
        if (this.btnGenEvening) {
            this.btnGenEvening.addEventListener("click", () => this.generateBriefing("evening"));
        }
        if (this.btnSpeakBriefing) {
            this.btnSpeakBriefing.addEventListener("click", () => this.speakCurrentBriefing());
        }

        // Notification Events
        if (this.btnDismissAllNotifs) {
            this.btnDismissAllNotifs.addEventListener("click", () => this.dismissAllNotifications());
        }

        // Initial background status check
        this.refreshBadgeCount();
        setInterval(() => this.refreshBadgeCount(), 30000);
    }

    open() {
        if (this.overlay) {
            this.overlay.style.display = "flex";
            this.loadProfile();
            this.loadPreferences();
            this.loadReminders();
            this.loadProactiveStatus();
            this.loadNotifications();
        }
    }

    close() {
        if (this.overlay) {
            this.overlay.style.display = "none";
        }
    }

    switchTab(tabId) {
        this.tabBtns.forEach(btn => {
            btn.classList.toggle("active", btn.getAttribute("data-tab") === tabId);
        });
        this.tabContents.forEach(pane => {
            if (pane.id === tabId) {
                pane.style.display = "block";
                pane.classList.add("active");
            } else {
                pane.style.display = "none";
                pane.classList.remove("active");
            }
        });
    }

    showMessage(text, isError = false) {
        if (!this.statusBanner || !this.statusText) return;
        this.statusText.textContent = text;
        this.statusBanner.className = isError ? "personalization-status-banner error" : "personalization-status-banner success";
        this.statusBanner.style.display = "block";
        setTimeout(() => {
            if (this.statusBanner) this.statusBanner.style.display = "none";
        }, 5000);
    }

    // =========================================================================
    // Profile Management
    // =========================================================================

    async loadProfile() {
        try {
            const res = await fetch("/api/personalization/profile");
            const data = await res.json();
            if (data.status === "success" && data.profile) {
                const p = data.profile;
                if (this.profUserName) this.profUserName.value = p.user_name || "";
                if (this.profPreferredAddress) this.profPreferredAddress.value = p.preferred_address || "";
                if (this.profRole) this.profRole.value = p.role || "";
                if (this.profTimezone) this.profTimezone.value = p.timezone || "Asia/Kolkata";
                if (this.profCommStyle) this.profCommStyle.value = p.communication_style || "concise";
                if (this.profTone) this.profTone.value = p.tone || "iron_man_witty";
                if (this.profVerbosity) this.profVerbosity.value = p.verbosity || "medium";
                if (this.profWakeWord) this.profWakeWord.value = p.wake_word_preference || "hey tony";
            }
        } catch (err) {
            console.error("Failed to load profile:", err);
        }
    }

    async saveProfile() {
        try {
            const payload = {
                user_name: this.profUserName ? this.profUserName.value.trim() : "",
                preferred_address: this.profPreferredAddress ? this.profPreferredAddress.value.trim() : "",
                role: this.profRole ? this.profRole.value.trim() : "",
                timezone: this.profTimezone ? this.profTimezone.value.trim() : "Asia/Kolkata",
                communication_style: this.profCommStyle ? this.profCommStyle.value : "concise",
                tone: this.profTone ? this.profTone.value : "iron_man_witty",
                verbosity: this.profVerbosity ? this.profVerbosity.value : "medium",
                wake_word_preference: this.profWakeWord ? this.profWakeWord.value.trim() : "hey tony"
            };

            const res = await fetch("/api/personalization/profile", {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (res.ok && data.status === "success") {
                this.showMessage("Profile updated successfully.");
            } else {
                this.showMessage(data.error || "Failed to update profile.", true);
            }
        } catch (err) {
            this.showMessage("Network error saving profile.", true);
        }
    }

    async resetPersonalization() {
        if (!confirm("Are you sure you want to reset all personalization data and profile back to factory defaults?")) return;
        try {
            const res = await fetch("/api/personalization/reset", { method: "POST" });
            const data = await res.json();
            if (res.ok) {
                this.showMessage("Personalization reset to defaults.");
                this.loadProfile();
                this.loadPreferences();
                this.loadReminders();
            } else {
                this.showMessage(data.error || "Reset failed.", true);
            }
        } catch (err) {
            this.showMessage("Error during factory reset.", true);
        }
    }

    // =========================================================================
    // Preferences Management
    // =========================================================================

    async loadPreferences() {
        if (!this.prefsListContainer) return;
        try {
            const res = await fetch("/api/personalization/preferences");
            const data = await res.json();
            if (data.status === "success") {
                const prefs = data.preferences || [];
                if (prefs.length === 0) {
                    this.prefsListContainer.innerHTML = '<div class="empty-state">No custom preferences stored.</div>';
                    return;
                }

                let html = '<table class="hud-table"><thead><tr><th>Key</th><th>Value</th><th>Category</th><th>Source</th><th>Action</th></tr></thead><tbody>';
                prefs.forEach(p => {
                    html += `<tr>
                        <td><code>${this.escapeHtml(p.key)}</code></td>
                        <td>${this.escapeHtml(String(p.value))}</td>
                        <td><span class="category-tag">${this.escapeHtml(p.category)}</span></td>
                        <td>${this.escapeHtml(p.source || "user_stated")}</td>
                        <td><button class="btn-del-pref hud-btn hud-btn-small hud-btn-danger" data-key="${this.escapeHtml(p.key)}">Delete</button></td>
                    </tr>`;
                });
                html += '</tbody></table>';
                this.prefsListContainer.innerHTML = html;

                this.prefsListContainer.querySelectorAll(".btn-del-pref").forEach(btn => {
                    btn.addEventListener("click", () => {
                        const key = btn.getAttribute("data-key");
                        this.deletePreference(key);
                    });
                });
            }
        } catch (err) {
            console.error("Failed to load preferences:", err);
        }
    }

    async savePreference() {
        if (!this.prefKey || !this.prefVal) return;
        const key = this.prefKey.value.trim();
        const value = this.prefVal.value.trim();
        const category = this.prefCat ? this.prefCat.value : "general";

        if (!key || !value) {
            this.showMessage("Key and Value are required.", true);
            return;
        }

        try {
            const res = await fetch("/api/personalization/preferences", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ key, value, category })
            });
            const data = await res.json();
            if (res.ok && data.status === "success") {
                this.showMessage(`Preference '${key}' saved.`);
                this.prefKey.value = "";
                this.prefVal.value = "";
                this.loadPreferences();
            } else {
                this.showMessage(data.error || "Failed to set preference.", true);
            }
        } catch (err) {
            this.showMessage("Network error saving preference.", true);
        }
    }

    async deletePreference(key) {
        try {
            const res = await fetch(`/api/personalization/preferences/${encodeURIComponent(key)}`, {
                method: "DELETE"
            });
            const data = await res.json();
            if (res.ok) {
                this.showMessage(`Preference '${key}' deleted.`);
                this.loadPreferences();
            } else {
                this.showMessage(data.error || "Delete failed.", true);
            }
        } catch (err) {
            this.showMessage("Error deleting preference.", true);
        }
    }

    // =========================================================================
    // Reminders & Scheduling
    // =========================================================================

    async loadReminders() {
        if (!this.remindersListContainer) return;
        try {
            const res = await fetch("/api/personalization/reminders");
            const data = await res.json();
            if (data.status === "success") {
                const reminders = data.reminders || [];
                if (reminders.length === 0) {
                    this.remindersListContainer.innerHTML = '<div class="empty-state">No scheduled reminders found.</div>';
                    return;
                }

                let html = "";
                reminders.forEach(r => {
                    const statusClass = `status-${r.status}`;
                    const recurrenceBadge = r.recurrence && r.recurrence !== "none" ? `<span class="recurrence-tag">${r.recurrence}</span>` : "";
                    html += `
                    <div class="reminder-card ${statusClass}">
                        <div class="reminder-card-top">
                            <span class="reminder-title">${this.escapeHtml(r.title)}</span>
                            <div class="reminder-tags">
                                ${recurrenceBadge}
                                <span class="badge ${statusClass}">${r.status.toUpperCase()}</span>
                            </div>
                        </div>
                        <div class="reminder-card-meta">
                            <span>Due: ${this.escapeHtml(r.due_time || "N/A")}</span>
                            ${r.priority ? `<span class="priority-tag">${r.priority}</span>` : ""}
                        </div>
                        <div class="reminder-card-actions">
                            ${r.status === 'pending' || r.status === 'snoozed' ? `
                                <button class="hud-btn hud-btn-small btn-complete-rem" data-id="${r.id}">Done</button>
                                <button class="hud-btn hud-btn-small btn-snooze-rem" data-id="${r.id}" data-mins="10">+10m</button>
                                <button class="hud-btn hud-btn-small btn-snooze-rem" data-id="${r.id}" data-mins="60">+1h</button>
                                <button class="hud-btn hud-btn-small hud-btn-danger btn-cancel-rem" data-id="${r.id}">Cancel</button>
                            ` : `
                                <span class="action-resolved">Completed</span>
                            `}
                        </div>
                    </div>`;
                });
                this.remindersListContainer.innerHTML = html;

                // Bind actions
                this.remindersListContainer.querySelectorAll(".btn-complete-rem").forEach(btn => {
                    btn.addEventListener("click", () => this.completeReminder(btn.getAttribute("data-id")));
                });
                this.remindersListContainer.querySelectorAll(".btn-snooze-rem").forEach(btn => {
                    btn.addEventListener("click", () => {
                        const rId = btn.getAttribute("data-id");
                        const mins = parseInt(btn.getAttribute("data-mins") || "10", 10);
                        this.snoozeReminder(rId, mins);
                    });
                });
                this.remindersListContainer.querySelectorAll(".btn-cancel-rem").forEach(btn => {
                    btn.addEventListener("click", () => this.cancelReminder(btn.getAttribute("data-id")));
                });
            }
        } catch (err) {
            console.error("Failed to load reminders:", err);
        }
    }

    async createReminder() {
        if (!this.remTitle) return;
        const title = this.remTitle.value.trim();
        const dueTime = this.remDueTime ? this.remDueTime.value.trim() : "";
        const recurrence = this.remRecurrence ? this.remRecurrence.value : "none";

        if (!title) {
            this.showMessage("Reminder title / instruction is required.", true);
            return;
        }

        try {
            const res = await fetch("/api/personalization/reminders", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: title,
                    due_time: dueTime || undefined,
                    recurrence: recurrence
                })
            });
            const data = await res.json();
            if (res.ok && data.status === "success") {
                this.showMessage(`Reminder scheduled for ${data.reminder.due_time}`);
                this.remTitle.value = "";
                if (this.remDueTime) this.remDueTime.value = "";
                this.loadReminders();
                this.refreshBadgeCount();
            } else {
                this.showMessage(data.error || "Failed to schedule reminder.", true);
            }
        } catch (err) {
            this.showMessage("Network error scheduling reminder.", true);
        }
    }

    async completeReminder(reminderId) {
        try {
            const res = await fetch(`/api/personalization/reminders/${encodeURIComponent(reminderId)}/complete`, {
                method: "POST"
            });
            const data = await res.json();
            if (res.ok) {
                this.showMessage("Reminder marked complete.");
                this.loadReminders();
                this.refreshBadgeCount();
            } else {
                this.showMessage(data.error || "Action failed.", true);
            }
        } catch (err) {
            this.showMessage("Error updating reminder.", true);
        }
    }

    async snoozeReminder(reminderId, minutes) {
        try {
            const res = await fetch(`/api/personalization/reminders/${encodeURIComponent(reminderId)}/snooze`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ minutes: minutes })
            });
            const data = await res.json();
            if (res.ok) {
                this.showMessage(`Reminder snoozed for ${minutes} minutes.`);
                this.loadReminders();
            } else {
                this.showMessage(data.error || "Snooze failed.", true);
            }
        } catch (err) {
            this.showMessage("Error snoozing reminder.", true);
        }
    }

    async cancelReminder(reminderId) {
        try {
            const res = await fetch(`/api/personalization/reminders/${encodeURIComponent(reminderId)}`, {
                method: "DELETE"
            });
            const data = await res.json();
            if (res.ok) {
                this.showMessage("Reminder cancelled.");
                this.loadReminders();
                this.refreshBadgeCount();
            } else {
                this.showMessage(data.error || "Cancel failed.", true);
            }
        } catch (err) {
            this.showMessage("Error cancelling reminder.", true);
        }
    }

    // =========================================================================
    // Routines Execution
    // =========================================================================

    async runRoutine(routineName) {
        if (!this.routineResultBox || !this.routineResultText) return;
        this.routineResultBox.style.display = "block";
        this.routineResultText.textContent = `Executing routine '${routineName}'...`;

        try {
            const res = await fetch(`/api/personalization/routines/${encodeURIComponent(routineName)}/run`, {
                method: "POST"
            });
            const data = await res.json();
            if (res.ok && data.status === "success") {
                this.routineResultText.textContent = JSON.stringify(data, null, 2);
                this.showMessage(`Routine '${routineName}' executed successfully.`);
                this.loadReminders();
            } else {
                this.routineResultText.textContent = `Error: ${data.error || "Routine failed"}`;
                this.showMessage(data.error || "Routine execution failed.", true);
            }
        } catch (err) {
            this.routineResultText.textContent = `Network error running routine: ${err.message}`;
            this.showMessage("Network error running routine.", true);
        }
    }

    // =========================================================================
    // Proactive Intelligence & Grounded Briefings
    // =========================================================================

    async loadProactiveStatus() {
        try {
            const res = await fetch("/api/personalization/proactive");
            const data = await res.json();
            if (data.status === "success" && data.proactive) {
                const p = data.proactive;
                if (this.proactiveToggle) {
                    this.proactiveToggle.checked = !!p.enabled;
                }
                if (this.proactiveStatusText) {
                    this.proactiveStatusText.textContent = p.enabled ? "PROACTIVE: ON" : "PROACTIVE: OFF";
                    this.proactiveStatusText.style.color = p.enabled ? "var(--jarvis-cyan)" : "var(--jarvis-text-muted)";
                }
                if (this.dispQuietHours && p.quiet_hours) {
                    this.dispQuietHours.textContent = `${p.quiet_hours.start} - ${p.quiet_hours.end}`;
                }
                if (this.dispMaxActions && p.daily_limit !== undefined) {
                    this.dispMaxActions.textContent = `${p.daily_count || 0} / ${p.daily_limit}`;
                }
            }
        } catch (err) {
            console.error("Failed to load proactive status:", err);
        }
    }

    async toggleProactive(enable) {
        try {
            const res = await fetch("/api/personalization/proactive/toggle", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enable: enable })
            });
            const data = await res.json();
            if (res.ok && data.status === "success") {
                this.showMessage(`Proactive intelligence ${enable ? "enabled" : "disabled"}.`);
                this.loadProactiveStatus();
            } else {
                this.showMessage(data.error || "Failed to toggle proactive mode.", true);
                if (this.proactiveToggle) this.proactiveToggle.checked = !enable;
            }
        } catch (err) {
            this.showMessage("Network error toggling proactive mode.", true);
            if (this.proactiveToggle) this.proactiveToggle.checked = !enable;
        }
    }

    async generateBriefing(type) {
        if (!this.briefingShowcase || !this.briefingBody) return;
        this.briefingShowcase.style.display = "block";
        if (this.briefingTitle) this.briefingTitle.textContent = type === "morning" ? "GROUNDED MORNING BRIEFING" : "GROUNDED EVENING SUMMARY";
        this.briefingBody.innerHTML = '<span class="spinner"></span> Synthesizing grounded briefing from real system telemetry...';

        try {
            const res = await fetch(`/api/personalization/briefing?type=${encodeURIComponent(type)}`);
            const data = await res.json();
            if (res.ok && data.status === "success" && data.briefing) {
                const b = data.briefing;
                this.currentBriefingText = b.spoken_text || b.text || "";
                this.briefingBody.innerHTML = `<div class="briefing-content">${this.escapeHtml(this.currentBriefingText).replace(/\n/g, '<br>')}</div>`;
            } else {
                this.briefingBody.innerHTML = `<div class="error-text">Failed: ${data.error || "Briefing generation failed"}</div>`;
            }
        } catch (err) {
            this.briefingBody.innerHTML = `<div class="error-text">Network error generating briefing: ${err.message}</div>`;
        }
    }

    speakCurrentBriefing() {
        if (!this.currentBriefingText) return;
        if (window.TonyAssistant && typeof window.TonyAssistant.speak === "function") {
            window.TonyAssistant.speak(this.currentBriefingText);
        } else {
            const audio = document.getElementById("tonyAudioPlayer");
            if (audio) {
                fetch("/api/voice/tts", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ text: this.currentBriefingText })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.status === "success" && data.audio_url) {
                        audio.src = data.audio_url;
                        audio.play();
                    }
                })
                .catch(e => console.error("TTS speech error:", e));
            }
        }
    }

    // =========================================================================
    // Notifications & History
    // =========================================================================

    async loadNotifications() {
        if (!this.notificationsListContainer) return;
        try {
            const res = await fetch("/api/personalization/notifications");
            const data = await res.json();
            if (data.status === "success") {
                const notifs = data.notifications || [];
                if (notifs.length === 0) {
                    this.notificationsListContainer.innerHTML = '<div class="empty-state">No notifications recorded yet.</div>';
                    return;
                }

                let html = "";
                notifs.forEach(n => {
                    html += `
                    <div class="notification-item status-${n.status}">
                        <div class="notification-top">
                            <span class="notification-title">${this.escapeHtml(n.title)}</span>
                            <span class="notification-time">${this.escapeHtml(n.created_at || "")}</span>
                        </div>
                        <div class="notification-body">${this.escapeHtml(n.body)}</div>
                    </div>`;
                });
                this.notificationsListContainer.innerHTML = html;
            }
        } catch (err) {
            console.error("Failed to load notifications:", err);
        }
    }

    async dismissAllNotifications() {
        try {
            const res = await fetch("/api/personalization/notifications/dismiss-all", { method: "POST" });
            if (res.ok) {
                this.showMessage("All notifications dismissed.");
                this.loadNotifications();
                this.refreshBadgeCount();
            }
        } catch (err) {
            this.showMessage("Failed to dismiss notifications.", true);
        }
    }

    async refreshBadgeCount() {
        if (!this.badgeCount) return;
        try {
            const res = await fetch("/api/personalization/health");
            const data = await res.json();
            if (data.status === "healthy") {
                const count = (data.pending_reminders || 0) + (data.delivered_notifications || 0);
                if (count > 0) {
                    this.badgeCount.textContent = count > 99 ? "99+" : String(count);
                    this.badgeCount.style.display = "inline-block";
                } else {
                    this.badgeCount.style.display = "none";
                }
            }
        } catch (err) {
            // Silently ignore health check errors
        }
    }

    escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
}

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
    window.tonyPersonalization = new TonyPersonalizationStudio();
});
