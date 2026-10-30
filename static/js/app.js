/**
 * TONY AI Assistant - Stage 1 Client Application
 * Handles chat communication, telemetry updates, UI rendering, and user interactions.
 */

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const chatForm = document.getElementById("chatForm");
    const messageInput = document.getElementById("messageInput");
    const sendBtn = document.getElementById("sendBtn");
    const chatViewport = document.getElementById("chatViewport");
    const messageStream = document.getElementById("messageStream");
    const welcomeHero = document.getElementById("welcomeHero");
    const typingIndicator = document.getElementById("typingIndicator");
    const errorBanner = document.getElementById("errorBanner");
    const errorMessage = document.getElementById("errorMessage");
    const errorDismiss = document.getElementById("errorDismiss");
    const clearBtn = document.getElementById("clearBtn");
    const hudProviderVal = document.getElementById("hudProviderVal");
    const hudModelVal = document.getElementById("hudModelVal");
    const sysStatusDot = document.getElementById("sysStatusDot");
    const sysStatusText = document.getElementById("sysStatusText");

    let isProcessing = false;

    // Format ISO or Date string into clean local time
    function formatTime(isoString) {
        if (!isoString) return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        try {
            const date = new Date(isoString);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
            return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
    }

    // Escape HTML to prevent injection while preserving text formatting
    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    // Auto-scroll chat to bottom
    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatViewport.scrollTop = chatViewport.scrollHeight;
        });
    }

    // Show / Hide UI States
    function setTyping(active) {
        isProcessing = active;
        if (active) {
            typingIndicator.classList.add("active");
            sendBtn.disabled = true;
        } else {
            typingIndicator.classList.remove("active");
            sendBtn.disabled = false;
        }
        scrollToBottom();
    }

    function showError(message) {
        errorMessage.textContent = message;
        errorBanner.classList.add("active");
        scrollToBottom();
    }

    function hideError() {
        errorBanner.classList.remove("active");
    }

    errorDismiss.addEventListener("click", hideError);

    // Render a message row in the stream
    function renderMessage(role, text, timestamp, metadata = {}) {
        if (welcomeHero) {
            welcomeHero.style.display = "none";
        }

        const isUser = role === "user";
        const row = document.createElement("div");
        row.className = `message-row ${isUser ? "user" : "assistant"}`;

        const avatar = document.createElement("div");
        avatar.className = "message-avatar";
        avatar.textContent = isUser ? "U" : "T";

        const bubbleWrapper = document.createElement("div");
        bubbleWrapper.className = "message-bubble-wrapper";

        const meta = document.createElement("div");
        meta.className = "message-meta";
        const timeFormatted = formatTime(timestamp);

        if (isUser) {
            meta.innerHTML = `<span>${timeFormatted}</span> &bull; <span>OPERATOR</span>`;
        } else {
            const providerTag = metadata.model ? `[${metadata.model}]` : "";
            meta.innerHTML = `<span>TONY CORE</span> ${providerTag ? `<span>${providerTag}</span>` : ""} &bull; <span>${timeFormatted}</span>`;
        }

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        // Preserve linebreaks safely
        bubble.innerHTML = escapeHtml(text).replace(/\n/g, "<br>");

        bubbleWrapper.appendChild(meta);
        bubbleWrapper.appendChild(bubble);

        // Render inline Image Generation Card if present (Stage 6)
        if (metadata.image_result) {
            const imgData = metadata.image_result;
            const imgCard = document.createElement("div");
            imgCard.className = "inline-image-card";

            const isMock = imgData.provider === "mock";
            const badgeClass = isMock ? "caption-label mock-badge" : "caption-label";
            const badgeText = isMock ? "SIMULATED TEST ASSET (OFFLINE MOCK)" : `GENERATED VISUAL ASSET (${escapeHtml((imgData.provider || "").toUpperCase())} • ${escapeHtml(imgData.model || "")})`;
            const mockNotice = isMock ? `<div class="caption-mock-notice">ℹ️ Offline mock engine active (blue cybernetic grid). Configure IMAGE_API_KEY in .env for real AI generation.</div>` : "";

            imgCard.innerHTML = `
                <div class="inline-image-thumb-box" title="Click to view full image">
                    <img src="${escapeHtml(imgData.url)}" alt="${escapeHtml(imgData.prompt)}" class="inline-image-thumb">
                    <div class="inline-image-overlay">
                        <span>🔍 Full View</span>
                    </div>
                </div>
                <div class="inline-image-caption">
                    <div class="${badgeClass}">${badgeText}</div>
                    <div class="caption-prompt">"${escapeHtml(imgData.prompt)}"</div>
                    ${mockNotice}
                    <div class="inline-image-actions">
                        <button type="button" class="btn-img-action btn-img-view">View Full</button>
                        <a href="${escapeHtml(imgData.url)}" download="${escapeHtml(imgData.filename)}" class="btn-img-action btn-img-download">Download</a>
                    </div>
                </div>
            `;

            imgCard.querySelector(".inline-image-thumb-box").addEventListener("click", () => {
                if (window.tonyOpenImageLightbox) window.tonyOpenImageLightbox(imgData);
            });
            imgCard.querySelector(".btn-img-view").addEventListener("click", () => {
                if (window.tonyOpenImageLightbox) window.tonyOpenImageLightbox(imgData);
            });

            bubbleWrapper.appendChild(imgCard);
        }

        // Render inline Video Generation Card if present (Stage 7)
        if (metadata.video_job) {
            const jobData = metadata.video_job;
            const vidCard = document.createElement("div");
            vidCard.className = "inline-video-card";
            const genId = jobData.generation_id;

            vidCard.innerHTML = `
                <div class="inline-video-header">
                    <span class="vid-badge">VIDEO ASYNCHRONOUS JOB</span>
                    <span class="vid-job-id">${escapeHtml(genId)}</span>
                </div>
                <div class="inline-video-body" id="videoBody_${genId}">
                    <div class="video-job-spinner-row">
                        <span class="video-job-spinner"></span>
                        <span class="video-job-status-msg" id="videoMsg_${genId}">Queued for background generation...</span>
                    </div>
                </div>
            `;
            bubbleWrapper.appendChild(vidCard);

            if (window.tonyPollVideoJob) {
                window.tonyPollVideoJob(genId, (completedVideo) => {
                    const bodyEl = document.getElementById(`videoBody_${genId}`);
                    if (bodyEl && completedVideo) {
                        bodyEl.innerHTML = `
                            <div class="inline-video-player-box">
                                <video controls playsinline preload="metadata" class="inline-video-player" src="${escapeHtml(completedVideo.url)}"></video>
                            </div>
                            <div class="inline-video-caption">
                                <div class="caption-label">GENERATED VIDEO ASSET (${completedVideo.duration}s • ${completedVideo.width}x${completedVideo.height})</div>
                                <div class="caption-prompt">"${escapeHtml(completedVideo.prompt)}"</div>
                                <div class="inline-video-actions">
                                    <a href="${escapeHtml(completedVideo.url)}" download="${escapeHtml(completedVideo.filename)}" class="btn-vid-action btn-vid-download">Download</a>
                                    <button type="button" class="btn-vid-action btn-vid-studio">Open in Studio</button>
                                </div>
                            </div>
                        `;
                        const studioBtn = bodyEl.querySelector(".btn-vid-studio");
                        if (studioBtn && window.tonyOpenVideoStudio) {
                            studioBtn.addEventListener("click", window.tonyOpenVideoStudio);
                        }
                    }
                });
            }
        }

        // Render inline Task Plan Card if present (Stage 8)
        if (metadata.task_plan && window.tonyRenderTaskCard) {
            window.tonyRenderTaskCard(metadata.task_plan, bubbleWrapper);
        }

        row.appendChild(avatar);
        row.appendChild(bubbleWrapper);

        messageStream.appendChild(row);
        scrollToBottom();
    }

    // Load Conversation History
    async function loadHistory() {
        try {
            const res = await fetch("/api/history");
            if (!res.ok) throw new Error("Could not load history");
            const data = await res.json();

            if (data.history && data.history.length > 0) {
                welcomeHero.style.display = "none";
                data.history.forEach(turn => {
                    renderMessage("user", turn.user_message, turn.timestamp);
                    renderMessage("assistant", turn.assistant_response, turn.timestamp);
                });
            } else {
                welcomeHero.style.display = "flex";
            }
        } catch (err) {
            console.warn("Failed to load initial history:", err);
        }
    }

    // Poll / Fetch System Diagnostic Status
    async function checkSystemStatus() {
        try {
            const res = await fetch("/api/status");
            if (!res.ok) throw new Error("Status endpoint error");
            const data = await res.json();

            if (data.provider) {
                hudProviderVal.textContent = data.provider.provider || "Active";
                hudModelVal.textContent = data.provider.model || "Default";

                if (data.provider.available) {
                    sysStatusDot.className = "status-dot online";
                    sysStatusText.className = "status-text";
                    sysStatusText.textContent = "ONLINE";
                } else {
                    sysStatusDot.className = "status-dot offline";
                    sysStatusText.className = "status-text offline";
                    sysStatusText.textContent = "ATTENTION";
                }
            }
        } catch (err) {
            sysStatusDot.className = "status-dot offline";
            sysStatusText.className = "status-text offline";
            sysStatusText.textContent = "OFFLINE";
        }
    }

    // Handle Form Submit
    async function handleSendMessage(rawText) {
        const text = rawText.trim();
        if (!text || isProcessing) return;

        hideError();
        const sendTimestamp = new Date().toISOString();

        // 1. Optimistic render of User message
        renderMessage("user", text, sendTimestamp);
        messageInput.value = "";
        messageInput.style.height = "auto";
        setTyping(true);
        if (window.tonySetOrbState) window.tonySetOrbState("thinking");

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ message: text })
            });

            const data = await response.json();

            if (!response.ok) {
                const errorDetail = data.error || `HTTP ${response.status}: Failed to transmit.`;
                showError(errorDetail);
                if (window.tonySetOrbState) window.tonySetOrbState("error");
                return;
            }

            // 2. Render TONY's response
            renderMessage("assistant", data.response, data.timestamp, {
                model: data.model,
                provider: data.provider,
                image_result: data.image_result,
                video_job: data.video_job,
                task_plan: data.task_plan
            });

            // If task is waiting for confirmation, reflect on orb
            if (data.task_plan && data.task_plan.status === "WAITING_CONFIRMATION") {
                if (window.tonySetOrbState) window.tonySetOrbState("waiting_confirmation");
            } else {
                if (window.tonySetOrbState) window.tonySetOrbState("idle");
            }

            // Dispatch global event for Stage 4 memory telemetry refresh
            window.dispatchEvent(new Event("tonyMessageCompleted"));

        } catch (networkError) {
            showError(`Network connection error: ${networkError.message}. Verify that the TONY backend server is running.`);
            if (window.tonySetOrbState) window.tonySetOrbState("error");
        } finally {
            setTyping(false);
            messageInput.focus();
        }
    }

    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        handleSendMessage(messageInput.value);
    });

    // Enter to Send, Shift+Enter for new line
    messageInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event("submit"));
        }
    });

    // Auto-grow textarea height
    messageInput.addEventListener("input", () => {
        messageInput.style.height = "auto";
        messageInput.style.height = `${Math.min(messageInput.scrollHeight, 120)}px`;
    });

    // Clear Session History
    clearBtn.addEventListener("click", async () => {
        if (!confirm("Clear current conversation history? (Previous data will be safely archived)")) {
            return;
        }

        try {
            const res = await fetch("/api/history", { method: "DELETE" });
            if (!res.ok) throw new Error("Failed to clear session.");
            messageStream.innerHTML = "";
            welcomeHero.style.display = "flex";
            hideError();
        } catch (err) {
            showError(`Could not clear history: ${err.message}`);
        }
    });

    // Quick Prompts Click
    document.querySelectorAll(".prompt-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            const prompt = chip.getAttribute("data-prompt");
            if (prompt) {
                handleSendMessage(prompt);
            }
        });
    });

    // Listen for external messages (e.g. from tool confirmation actions)
    window.addEventListener("tonyExternalMessage", (e) => {
        if (e.detail) {
            renderMessage(
                e.detail.role || "assistant",
                e.detail.text || "",
                new Date().toISOString(),
                { model: e.detail.model || "tool_confirmation" }
            );
        }
    });

    // Initialize
    loadHistory();
    checkSystemStatus();
    messageInput.focus();
});
