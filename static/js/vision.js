/**
 * TONY AI - Vision & Multimodal Intelligence Client Module (Stage 9)
 * Manages image upload, dropzone, visual inspection, question answering, OCR,
 * active generated-image analysis, and history display.
 */

class TonyVisionStudio {
    constructor() {
        this.selectedFile = null;
        this.useActiveImage = false;
        this.activeImageId = null;

        // Elements
        this.overlay = document.getElementById("visionModalOverlay");
        this.openBtn = document.getElementById("openVisionBtn");
        this.closeBtn = document.getElementById("closeVisionModalBtn");
        this.dropZone = document.getElementById("visionDropZone");
        this.fileInput = document.getElementById("visionFileInput");
        this.previewWrapper = document.getElementById("dropzonePreviewWrapper");
        this.previewImg = document.getElementById("visionImagePreview");
        this.btnClearPreview = document.getElementById("btnClearVisionPreview");
        this.queryInput = document.getElementById("visionQueryInput");

        // Action Buttons
        this.btnAnalyze = document.getElementById("btnVisionAnalyze");
        this.btnDescribe = document.getElementById("btnVisionDescribe");
        this.btnOCR = document.getElementById("btnVisionOCR");
        this.btnActiveImage = document.getElementById("btnVisionActiveImage");
        this.btnRefreshHistory = document.getElementById("refreshVisionHistoryBtn");

        // Status & Result
        this.loadingBanner = document.getElementById("visionLoadingBanner");
        this.loadingText = document.getElementById("visionLoadingText");
        this.errorBanner = document.getElementById("visionErrorBanner");
        this.errorMessage = document.getElementById("visionErrorMessage");
        this.resultShowcase = document.getElementById("visionResultShowcase");
        this.resultBody = document.getElementById("visionResultBody");
        this.resultMeta = document.getElementById("visionResultMeta");
        this.historyList = document.getElementById("visionHistoryList");
        this.modelIndicator = document.getElementById("visionModelIndicator");

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

        // Quick action button
        const quickVision = document.querySelector('[data-action="vision"]');
        if (quickVision) {
            quickVision.addEventListener("click", () => this.open());
        }

        // Dropzone & File selection
        if (this.dropZone && this.fileInput) {
            this.dropZone.addEventListener("click", (e) => {
                if (e.target !== this.btnClearPreview && !this.selectedFile && !this.useActiveImage) {
                    this.fileInput.click();
                }
            });

            this.fileInput.addEventListener("change", (e) => {
                if (e.target.files && e.target.files[0]) {
                    this.handleFileSelected(e.target.files[0]);
                }
            });

            this.dropZone.addEventListener("dragover", (e) => {
                e.preventDefault();
                this.dropZone.classList.add("dragover");
            });

            this.dropZone.addEventListener("dragleave", () => {
                this.dropZone.classList.remove("dragover");
            });

            this.dropZone.addEventListener("drop", (e) => {
                e.preventDefault();
                this.dropZone.classList.remove("dragover");
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                    this.handleFileSelected(e.dataTransfer.files[0]);
                }
            });
        }

        if (this.btnClearPreview) {
            this.btnClearPreview.addEventListener("click", (e) => {
                e.stopPropagation();
                this.clearSelection();
            });
        }

        // Action Buttons
        if (this.btnAnalyze) {
            this.btnAnalyze.addEventListener("click", () => this.executeAction("analyze"));
        }
        if (this.btnDescribe) {
            this.btnDescribe.addEventListener("click", () => this.executeAction("describe"));
        }
        if (this.btnOCR) {
            this.btnOCR.addEventListener("click", () => this.executeAction("ocr"));
        }
        if (this.btnActiveImage) {
            this.btnActiveImage.addEventListener("click", () => this.selectActiveImage());
        }
        if (this.btnRefreshHistory) {
            this.btnRefreshHistory.addEventListener("click", () => this.loadHistory());
        }

        // Enter key in query input
        if (this.queryInput) {
            this.queryInput.addEventListener("keydown", (e) => {
                if (e.key === "Enter") {
                    this.executeAction("question");
                }
            });
        }
    }

    open() {
        if (!this.overlay) return;
        this.overlay.style.display = "flex";
        this.checkHealth();
        this.loadHistory();
    }

    close() {
        if (!this.overlay) return;
        this.overlay.style.display = "none";
        this.hideError();
    }

    handleFileSelected(file) {
        // Format check
        const ext = file.name.split('.').pop().toLowerCase();
        if (!['png', 'jpg', 'jpeg', 'webp'].includes(ext)) {
            this.showError("Unsupported format. Please select a PNG, JPEG, or WebP image.");
            return;
        }

        // Size check (10MB)
        if (file.size > 10 * 1024 * 1024) {
            this.showError("Image file exceeds the 10 MB maximum size limit.");
            return;
        }

        this.selectedFile = file;
        this.useActiveImage = false;
        this.hideError();

        const reader = new FileReader();
        reader.onload = (e) => {
            this.previewImg.src = e.target.result;
            this.previewWrapper.style.display = "block";
            const promptEl = document.getElementById("dropzonePrompt");
            if (promptEl) promptEl.style.display = "none";
        };
        reader.readAsDataURL(file);
    }

    selectActiveImage() {
        this.useActiveImage = true;
        this.selectedFile = null;
        this.hideError();

        // Fetch active image thumbnail from latest generated image
        fetch("/api/images/history?limit=1")
            .then(res => res.json())
            .then(data => {
                if (data.success && data.records && data.records.length > 0) {
                    const activeRec = data.records[0];
                    this.activeImageId = activeRec.image_id;
                    this.previewImg.src = `/api/images/${activeRec.image_id}/file`;
                    this.previewWrapper.style.display = "block";
                    const promptEl = document.getElementById("dropzonePrompt");
                    if (promptEl) promptEl.style.display = "none";
                } else {
                    this.showError("No active generated image found. Generate an image first.");
                }
            })
            .catch(err => {
                this.showError("Failed to resolve active generated image: " + err.message);
            });
    }

    clearSelection() {
        this.selectedFile = null;
        this.useActiveImage = false;
        this.activeImageId = null;
        if (this.fileInput) this.fileInput.value = "";
        if (this.previewImg) this.previewImg.src = "";
        if (this.previewWrapper) this.previewWrapper.style.display = "none";
        const promptEl = document.getElementById("dropzonePrompt");
        if (promptEl) promptEl.style.display = "flex";
        this.hideError();
    }

    executeAction(actionType) {
        if (!this.selectedFile && !this.useActiveImage) {
            this.showError("Please upload an image or click 'Analyze Active Image'.");
            return;
        }

        const promptText = (this.queryInput ? this.queryInput.value : "").trim();
        let endpoint = "/api/vision/analyze";
        let task = "analyze";

        if (actionType === "describe") {
            task = "describe";
        } else if (actionType === "ocr") {
            endpoint = "/api/vision/ocr";
            task = "ocr";
        } else if (actionType === "question" || (actionType === "analyze" && promptText)) {
            task = promptText ? "question" : "analyze";
        }

        const formData = new FormData();
        if (this.selectedFile) {
            formData.append("file", this.selectedFile);
        } else if (this.useActiveImage) {
            formData.append("use_active", "true");
            if (this.activeImageId) formData.append("image_id", this.activeImageId);
        }

        formData.append("prompt", promptText);
        formData.append("task", task);

        this.showLoading(`TONY is processing ${task.toUpperCase()} request...`);
        this.hideError();

        fetch(endpoint, {
            method: "POST",
            body: formData
        })
            .then(async (res) => {
                const data = await res.json();
                if (!res.ok || !data.success) {
                    throw new Error(data.error || `HTTP ${res.status}`);
                }
                return data;
            })
            .then((data) => {
                this.hideLoading();
                this.displayResult(data.result);
                this.loadHistory();
            })
            .catch((err) => {
                this.hideLoading();
                this.showError(err.message);
            });
    }

    displayResult(result) {
        if (!result) return;
        if (this.resultShowcase) this.resultShowcase.style.display = "block";
        if (this.resultBody) this.resultBody.textContent = result.response;
        if (this.resultMeta) {
            this.resultMeta.textContent = `${result.provider} (${result.model}) | ${result.duration_seconds}s | Task: ${result.task}`;
        }
    }

    loadHistory() {
        if (!this.historyList) return;
        fetch("/api/vision/history?limit=15")
            .then(res => res.json())
            .then(data => {
                if (data.success && data.records) {
                    this.renderHistory(data.records);
                }
            })
            .catch(err => console.warn("Failed to load vision history:", err));
    }

    renderHistory(records) {
        if (!this.historyList) return;
        this.historyList.innerHTML = "";
        if (records.length === 0) {
            this.historyList.innerHTML = '<div class="empty-state">No past visual analyses recorded yet.</div>';
            return;
        }

        records.forEach(rec => {
            const card = document.createElement("div");
            card.className = "vision-history-card";
            card.innerHTML = `
                <div class="vh-header">
                    <span class="vh-task">${rec.task.toUpperCase()}</span>
                    <span class="vh-time">${new Date(rec.timestamp).toLocaleTimeString()}</span>
                </div>
                <div class="vh-body">${rec.response}</div>
                <div class="vh-footer">
                    <span>${rec.provider} (${rec.model})</span>
                    <span>${rec.duration_seconds}s</span>
                </div>
            `;
            this.historyList.appendChild(card);
        });
    }

    checkHealth() {
        fetch("/api/vision/health")
            .then(res => res.json())
            .then(data => {
                if (this.modelIndicator) {
                    const status = data.available ? "ONLINE" : "OFFLINE";
                    this.modelIndicator.textContent = `${data.provider} (${data.model}) [${status}]`;
                }
            })
            .catch(() => {
                if (this.modelIndicator) {
                    this.modelIndicator.textContent = "Vision Engine Offline";
                }
            });
    }

    showLoading(text) {
        if (this.loadingBanner) {
            this.loadingBanner.style.display = "flex";
            if (this.loadingText) this.loadingText.textContent = text || "Processing...";
        }
    }

    hideLoading() {
        if (this.loadingBanner) this.loadingBanner.style.display = "none";
    }

    showError(msg) {
        if (this.errorBanner) {
            this.errorBanner.style.display = "flex";
            if (this.errorMessage) this.errorMessage.textContent = msg;
        }
    }

    hideError() {
        if (this.errorBanner) this.errorBanner.style.display = "none";
    }
}

// Instantiate on DOM ready
document.addEventListener("DOMContentLoaded", () => {
    window.tonyVision = new TonyVisionStudio();
});
