/**
 * TONY AI Assistant - Stage 7 Video Generation & Studio Client Controller
 * Manages Video Studio modal, async job creation, polling, HTML5 video player,
 * thumbnail previews, cancellation, regeneration, deletion, and cross-stage image animation.
 */

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const openVideosBtn = document.getElementById("openVideosBtn");
    const closeVideosBtn = document.getElementById("closeVideosBtn");
    const videosModalOverlay = document.getElementById("videosModalOverlay");
    const videosGalleryContainer = document.getElementById("videosGalleryContainer");
    const modalVideoCountBadge = document.getElementById("modalVideoCountBadge");
    const hudVideoCountVal = document.getElementById("hudVideoCountVal");
    const studioVideoPromptInput = document.getElementById("studioVideoPromptInput");
    const videoDurationSelect = document.getElementById("videoDurationSelect");
    const videoAspectSelect = document.getElementById("videoAspectSelect");
    const videoAnimateImageCheck = document.getElementById("videoAnimateImageCheck");
    const studioVideoGenerateBtn = document.getElementById("studioVideoGenerateBtn");
    const studioVideoCancelBtn = document.getElementById("studioVideoCancelBtn");
    const refreshVideosBtn = document.getElementById("refreshVideosBtn");
    const toggleHardwareDiagBtn = document.getElementById("toggleHardwareDiagBtn");
    const videoDiagPanel = document.getElementById("videoDiagPanel");
    const diagHfBody = document.getElementById("diagHfBody");
    const diagLocalBody = document.getElementById("diagLocalBody");

    // Progress Elements
    const videoProgressContainer = document.getElementById("videoProgressContainer");
    const videoProgressStatusText = document.getElementById("videoProgressStatusText");
    const videoProgressPctText = document.getElementById("videoProgressPctText");
    const videoProgressFill = document.getElementById("videoProgressFill");

    // Showcase Player Elements
    const videoPlayerShowcase = document.getElementById("videoPlayerShowcase");
    const studioVideoPlayer = document.getElementById("studioVideoPlayer");
    const showcasePrompt = document.getElementById("showcasePrompt");
    const showcaseDetails = document.getElementById("showcaseDetails");
    const showcaseRegenBtn = document.getElementById("showcaseRegenBtn");
    const showcaseDownloadBtn = document.getElementById("showcaseDownloadBtn");
    const showcaseDeleteBtn = document.getElementById("showcaseDeleteBtn");

    let currentShowcaseVideo = null;
    let activeGenerationId = null;
    let pollInterval = null;

    // Format ISO string to clean local date/time
    function formatTime(isoString) {
        if (!isoString) return "";
        try {
            const d = new Date(isoString);
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + " " + d.toLocaleDateString([], { month: 'short', day: 'numeric' });
        } catch {
            return isoString;
        }
    }

    // Escape HTML
    function escapeHtml(text) {
        if (!text) return "";
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    // Open / Close Studio Modal
    function openStudio() {
        if (videosModalOverlay) {
            videosModalOverlay.classList.add("active");
            loadVideos();
            if (studioVideoPromptInput) studioVideoPromptInput.focus();
        }
    }

    function closeStudio() {
        if (videosModalOverlay) {
            videosModalOverlay.classList.remove("active");
            if (studioVideoPlayer) {
                studioVideoPlayer.pause();
            }
        }
    }

    if (openVideosBtn) openVideosBtn.addEventListener("click", openStudio);
    if (closeVideosBtn) closeVideosBtn.addEventListener("click", closeStudio);

    if (videosModalOverlay) {
        videosModalOverlay.addEventListener("click", (e) => {
            if (e.target === videosModalOverlay) closeStudio();
        });
    }

    // Toggle Hardware & Provider Diagnostics Panel
    if (toggleHardwareDiagBtn) {
        toggleHardwareDiagBtn.addEventListener("click", async () => {
            if (videoDiagPanel.style.display === "none") {
                videoDiagPanel.style.display = "grid";
                await loadDiagnostics();
            } else {
                videoDiagPanel.style.display = "none";
            }
        });
    }

    async function loadDiagnostics() {
        try {
            const provRes = await fetch("/api/videos/providers");
            if (provRes.ok) {
                const provData = await provRes.json();
                const hf = provData.huggingface || {};
                diagHfBody.innerHTML = `
                    Status: <strong>${hf.available ? "Ready" : "Unavailable"}</strong><br>
                    Configured: <strong>${hf.configured ? "Yes" : "No Token"}</strong><br>
                    Mode: <em>Free Allowance</em><br>
                    Paid Fallback: <strong>${hf.paid_fallback ? "ON" : "OFF"}</strong>
                `;
            }

            const capRes = await fetch("/api/videos/local-capability");
            if (capRes.ok) {
                const cap = await capRes.json();
                diagLocalBody.innerHTML = `
                    GPU: <strong>${escapeHtml(cap.gpu_name || "None")}</strong><br>
                    CUDA: <strong>${cap.cuda_available ? "Yes" : "No"}</strong><br>
                    VRAM: <strong>${cap.vram_mb || 0} MB</strong><br>
                    Available: <strong>${cap.provider_available ? "Yes" : "No"}</strong>
                `;
            }
        } catch (err) {
            console.warn("Could not load video diagnostics:", err);
        }
    }

    // Load and Render Video Gallery
    async function loadVideos() {
        try {
            const res = await fetch("/api/videos?limit=50");
            if (!res.ok) throw new Error("Failed to load videos");
            const data = await res.json();

            const videos = data.videos || [];
            const count = data.total || videos.length;

            if (modalVideoCountBadge) modalVideoCountBadge.textContent = `${count} VIDEOS`;
            if (hudVideoCountVal) hudVideoCountVal.textContent = count;

            renderGallery(videos);

            // Auto-load latest into player if not already playing
            if (!currentShowcaseVideo && videos.length > 0) {
                loadIntoPlayer(videos[0]);
            }
        } catch (err) {
            console.error("Error loading video history:", err);
            if (videosGalleryContainer) {
                videosGalleryContainer.innerHTML = `<div class="gallery-empty-state">Unable to load video history.</div>`;
            }
        }
    }

    function renderGallery(videos) {
        if (!videosGalleryContainer) return;

        if (videos.length === 0) {
            videosGalleryContainer.innerHTML = `
                <div class="gallery-empty-state">
                    <div class="empty-icon">🎬</div>
                    <div class="empty-title">NO VIDEOS GENERATED YET</div>
                    <div class="empty-sub">Type a prompt above or say "Tony, create a video of..." to begin.</div>
                </div>
            `;
            return;
        }

        videosGalleryContainer.innerHTML = "";
        videos.forEach(video => {
            const card = document.createElement("div");
            card.className = "video-card";
            if (currentShowcaseVideo && currentShowcaseVideo.video_id === video.video_id) {
                card.classList.add("active-video");
            }

            const thumbSrc = video.thumbnail_url || "/static/img/video_placeholder.png";
            const durationLabel = `${video.duration || 5}s`;
            const resolutionLabel = `${video.width}x${video.height}`;
            const providerTag = video.simulated ? `[MOCK]` : `[${video.provider.toUpperCase()}]`;

            card.innerHTML = `
                <div class="video-thumb-wrapper">
                    <img src="${escapeHtml(thumbSrc)}" alt="${escapeHtml(video.prompt)}" class="video-card-thumb" onerror="this.src='/static/img/video_placeholder.png'">
                    <span class="video-duration-badge">${durationLabel}</span>
                    <div class="video-card-overlay">
                        <span class="play-icon">▶ PLAY</span>
                    </div>
                </div>
                <div class="video-card-content">
                    <div class="video-card-prompt" title="${escapeHtml(video.prompt)}">"${escapeHtml(video.prompt)}"</div>
                    <div class="video-card-meta">
                        <span>${providerTag}</span> • <span>${resolutionLabel}</span> • <span>${formatTime(video.created_at)}</span>
                    </div>
                    <div class="video-card-actions">
                        <button type="button" class="btn-vid-action btn-play">Play</button>
                        <a href="${escapeHtml(video.url)}" download="${escapeHtml(video.filename)}" class="btn-vid-action btn-download">Download</a>
                        <button type="button" class="btn-vid-action btn-delete">Delete</button>
                    </div>
                </div>
            `;

            // Card click / Play click
            const playTarget = () => loadIntoPlayer(video);
            card.querySelector(".video-thumb-wrapper").addEventListener("click", playTarget);
            card.querySelector(".btn-play").addEventListener("click", playTarget);

            // Delete click
            card.querySelector(".btn-delete").addEventListener("click", async (e) => {
                e.stopPropagation();
                if (!confirm(`Delete video "${video.prompt.substring(0, 30)}..."?`)) return;
                try {
                    const delRes = await fetch(`/api/videos/${video.video_id}`, { method: "DELETE" });
                    if (!delRes.ok) throw new Error("Delete request failed");
                    if (currentShowcaseVideo && currentShowcaseVideo.video_id === video.video_id) {
                        videoPlayerShowcase.style.display = "none";
                        currentShowcaseVideo = null;
                    }
                    loadVideos();
                } catch (err) {
                    alert(`Could not delete video: ${err.message}`);
                }
            });

            videosGalleryContainer.appendChild(card);
        });
    }

    // Load video into HTML5 showcase player
    function loadIntoPlayer(video) {
        currentShowcaseVideo = video;
        if (!videoPlayerShowcase || !studioVideoPlayer) return;

        studioVideoPlayer.src = video.url;
        showcasePrompt.textContent = `"${video.prompt}"`;

        const detailsText = `ID: ${video.video_id} • Duration: ${video.duration}s (${video.fps} FPS) • Res: ${video.width}x${video.height} • Provider: ${video.provider} (${video.model}) ${video.simulated ? '[MOCK]' : ''}`;
        showcaseDetails.textContent = detailsText;

        showcaseDownloadBtn.href = video.url;
        showcaseDownloadBtn.setAttribute("download", video.filename || "tony_video.mp4");

        videoPlayerShowcase.style.display = "block";
        studioVideoPlayer.load();

        // Highlight card in gallery
        document.querySelectorAll(".video-card").forEach(c => c.classList.remove("active-video"));
    }

    // Showcase actions
    if (showcaseRegenBtn) {
        showcaseRegenBtn.addEventListener("click", async () => {
            if (!currentShowcaseVideo) return;
            try {
                const res = await fetch(`/api/videos/${currentShowcaseVideo.video_id}/regenerate`, { method: "POST" });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || "Regeneration failed");
                startPollingJob(data.generation_id);
            } catch (err) {
                alert(`Regeneration error: ${err.message}`);
            }
        });
    }

    if (showcaseDeleteBtn) {
        showcaseDeleteBtn.addEventListener("click", async () => {
            if (!currentShowcaseVideo) return;
            if (!confirm("Delete this video permanently?")) return;
            try {
                const res = await fetch(`/api/videos/${currentShowcaseVideo.video_id}`, { method: "DELETE" });
                if (!res.ok) throw new Error("Failed to delete video");
                videoPlayerShowcase.style.display = "none";
                currentShowcaseVideo = null;
                loadVideos();
            } catch (err) {
                alert(`Delete error: ${err.message}`);
            }
        });
    }

    // Start video generation job
    async function handleGenerateVideo() {
        const prompt = studioVideoPromptInput.value.trim();
        const animateImage = videoAnimateImageCheck ? videoAnimateImageCheck.checked : false;

        if (!prompt && !animateImage) {
            alert("Please enter a video prompt or check 'Animate Active Image'.");
            return;
        }

        const duration = parseInt(videoDurationSelect.value, 10) || 5;
        let width = 512, height = 512;
        if (videoAspectSelect.value === "cinematic") {
            width = 768; height = 432;
        } else if (videoAspectSelect.value === "vertical") {
            width = 432; height = 768;
        }

        studioVideoGenerateBtn.disabled = true;
        studioVideoCancelBtn.style.display = "inline-flex";

        try {
            const payload = {
                prompt: prompt || (animateImage ? "cinematic animation of the active image" : ""),
                duration: duration,
                width: width,
                height: height
            };

            if (animateImage) {
                payload.image_id = "active";
            }

            const res = await fetch("/api/videos/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || "Failed to start video generation.");
            }

            activeGenerationId = data.generation_id;
            startPollingJob(activeGenerationId);

        } catch (err) {
            alert(`Generation Error: ${err.message}`);
            resetGenerationUI();
        }
    }

    if (studioVideoGenerateBtn) {
        studioVideoGenerateBtn.addEventListener("click", handleGenerateVideo);
    }

    if (studioVideoPromptInput) {
        studioVideoPromptInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleGenerateVideo();
            }
        });
    }

    // Cancel Job
    if (studioVideoCancelBtn) {
        studioVideoCancelBtn.addEventListener("click", async () => {
            if (!activeGenerationId) return;
            try {
                await fetch(`/api/videos/${activeGenerationId}/cancel`, { method: "POST" });
                clearInterval(pollInterval);
                videoProgressStatusText.textContent = "Generation cancelled.";
                setTimeout(resetGenerationUI, 1500);
            } catch (err) {
                console.error("Cancellation error:", err);
            }
        });
    }

    if (refreshVideosBtn) {
        refreshVideosBtn.addEventListener("click", loadVideos);
    }

    function resetGenerationUI() {
        if (studioVideoGenerateBtn) studioVideoGenerateBtn.disabled = false;
        if (studioVideoCancelBtn) studioVideoCancelBtn.style.display = "none";
        if (videoProgressContainer) videoProgressContainer.style.display = "none";
        activeGenerationId = null;
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
    }

    // Poll in-flight video job
    function startPollingJob(genId, onCompleteCallback = null) {
        if (videoProgressContainer) {
            videoProgressContainer.style.display = "block";
            videoProgressFill.style.width = "5%";
            videoProgressStatusText.textContent = "Job queued for processing...";
            videoProgressPctText.textContent = "";
        }

        if (pollInterval) clearInterval(pollInterval);

        pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/videos/${genId}/status`);
                if (!res.ok) {
                    clearInterval(pollInterval);
                    return;
                }
                const data = await res.json();

                if (data.job_status === "processing") {
                    if (data.progress !== null) {
                        videoProgressFill.style.width = `${data.progress}%`;
                        videoProgressPctText.textContent = `${data.progress}%`;
                    } else {
                        videoProgressFill.style.width = "60%";
                        videoProgressPctText.textContent = "";
                    }
                    videoProgressStatusText.textContent = data.progress_message || "Generating video...";
                } else if (data.job_status === "completed") {
                    clearInterval(pollInterval);
                    videoProgressFill.style.width = "100%";
                    videoProgressStatusText.textContent = "Generation completed successfully!";
                    setTimeout(() => {
                        resetGenerationUI();
                        loadVideos();
                        if (data.video) {
                            loadIntoPlayer(data.video);
                            if (onCompleteCallback) onCompleteCallback(data.video);
                        }
                    }, 800);
                } else if (data.job_status === "failed") {
                    clearInterval(pollInterval);
                    videoProgressStatusText.textContent = `Failed: ${data.error || "Generation error"}`;
                    videoProgressFill.style.backgroundColor = "var(--color-danger, #e74c3c)";
                    setTimeout(resetGenerationUI, 3000);
                } else if (data.job_status === "cancelled") {
                    clearInterval(pollInterval);
                    videoProgressStatusText.textContent = "Job was cancelled.";
                    setTimeout(resetGenerationUI, 1500);
                }
            } catch (err) {
                console.warn("Polling error:", err);
            }
        }, 1500);
    }

    // Expose global polling hook for chat and voice messages
    window.tonyPollVideoJob = startPollingJob;
    window.tonyOpenVideoStudio = openStudio;
});
