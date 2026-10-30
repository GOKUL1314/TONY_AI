/**
 * TONY AI Assistant - Stage 6 Image Generation & Studio Client Controller
 * Manages Image Studio modal, gallery rendering, prompt generation,
 * regeneration, editing, lightbox zoom view, and inline chat image cards.
 */

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const openImagesBtn = document.getElementById("openImagesBtn");
    const closeImagesBtn = document.getElementById("closeImagesBtn");
    const imagesModalOverlay = document.getElementById("imagesModalOverlay");
    const imagesGalleryContainer = document.getElementById("imagesGalleryContainer");
    const modalImageCountBadge = document.getElementById("modalImageCountBadge");
    const hudImageCountVal = document.getElementById("hudImageCountVal");
    const studioPromptInput = document.getElementById("studioPromptInput");
    const studioGenerateBtn = document.getElementById("studioGenerateBtn");
    const refreshImagesBtn = document.getElementById("refreshImagesBtn");

    // Lightbox Elements
    const imageLightboxOverlay = document.getElementById("imageLightboxOverlay");
    const closeLightboxBtn = document.getElementById("closeLightboxBtn");
    const lightboxImg = document.getElementById("lightboxImg");
    const lightboxPrompt = document.getElementById("lightboxPrompt");
    const lightboxDetails = document.getElementById("lightboxDetails");
    const lightboxRegenBtn = document.getElementById("lightboxRegenBtn");
    const lightboxDownloadBtn = document.getElementById("lightboxDownloadBtn");
    const lightboxDeleteBtn = document.getElementById("lightboxDeleteBtn");

    let currentLightboxImage = null;
    let isGenerating = false;

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

    // Escape HTML for safe rendering
    function escapeHtml(text) {
        if (!text) return "";
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    // Open / Close Studio Modal
    function openStudio() {
        imagesModalOverlay.classList.add("active");
        loadImages();
        studioPromptInput.focus();
    }

    function closeStudio() {
        imagesModalOverlay.classList.remove("active");
    }

    if (openImagesBtn) openImagesBtn.addEventListener("click", openStudio);
    if (closeImagesBtn) closeImagesBtn.addEventListener("click", closeStudio);

    imagesModalOverlay.addEventListener("click", (e) => {
        if (e.target === imagesModalOverlay) closeStudio();
    });

    // Open / Close Lightbox
    function openLightbox(image) {
        currentLightboxImage = image;
        lightboxImg.src = image.url;
        lightboxPrompt.textContent = image.prompt;

        const isMock = image.provider === "mock";
        const provLabel = isMock ? "mock (Offline Simulation — Set IMAGE_API_KEY for real AI)" : `${image.provider} (${image.model})`;
        const detailsText = `ID: ${image.image_id} • Size: ${image.width}x${image.height} • Provider: ${provLabel} • Time: ${formatTime(image.created_at)}`;
        lightboxDetails.textContent = detailsText;

        lightboxDownloadBtn.href = image.url;
        lightboxDownloadBtn.setAttribute("download", image.filename || "tony_image.png");

        imageLightboxOverlay.style.display = "flex";
    }

    function closeLightbox() {
        imageLightboxOverlay.style.display = "none";
        currentLightboxImage = null;
        lightboxImg.src = "";
    }

    if (closeLightboxBtn) closeLightboxBtn.addEventListener("click", closeLightbox);
    imageLightboxOverlay.addEventListener("click", (e) => {
        if (e.target === imageLightboxOverlay) closeLightbox();
    });

    // Expose lightbox trigger globally for inline chat cards
    window.tonyOpenImageLightbox = openLightbox;

    // Load and Render Image Gallery
    async function loadImages() {
        try {
            imagesGalleryContainer.innerHTML = '<div class="gallery-loading">Scanning visual archives...</div>';
            const res = await fetch("/api/images?limit=50");
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            const images = data.images || [];
            updateImageCounters(data.total !== undefined ? data.total : images.length);

            if (images.length === 0) {
                imagesGalleryContainer.innerHTML = `
                    <div class="gallery-empty">
                        <div class="empty-icon">🎨</div>
                        <div class="empty-title">Visual Archive Empty</div>
                        <div class="empty-subtitle">Generate an image by typing "Tony, create an image of..." or enter a prompt above.</div>
                    </div>
                `;
                return;
            }

            imagesGalleryContainer.innerHTML = "";
            images.forEach(img => {
                const card = document.createElement("div");
                card.className = "image-card";

                const thumbWrapper = document.createElement("div");
                thumbWrapper.className = "image-thumb-wrapper";

                const thumb = document.createElement("img");
                thumb.className = "image-thumb";
                thumb.src = img.url;
                thumb.alt = escapeHtml(img.prompt);
                thumb.loading = "lazy";
                thumb.addEventListener("click", () => openLightbox(img));

                const hoverOverlay = document.createElement("div");
                hoverOverlay.className = "image-thumb-overlay";
                hoverOverlay.innerHTML = "<span>Inspect Asset</span>";
                hoverOverlay.addEventListener("click", () => openLightbox(img));

                thumbWrapper.appendChild(thumb);
                thumbWrapper.appendChild(hoverOverlay);

                const info = document.createElement("div");
                info.className = "image-info";

                const promptElem = document.createElement("div");
                promptElem.className = "image-prompt-text";
                promptElem.textContent = img.prompt;
                promptElem.title = img.prompt;

                const meta = document.createElement("div");
                meta.className = "image-meta-row";
                const mockBadge = img.provider === "mock" ? '<span class="mock-tag" title="Offline simulated image">[MOCK]</span> ' : '';
                meta.innerHTML = `${mockBadge}<span>${formatTime(img.created_at)}</span> &bull; <span>${img.width}x${img.height}</span>`;

                const actions = document.createElement("div");
                actions.className = "image-card-actions";

                const viewBtn = document.createElement("button");
                viewBtn.className = "card-action-btn";
                viewBtn.textContent = "View";
                viewBtn.addEventListener("click", () => openLightbox(img));

                const regenBtn = document.createElement("button");
                regenBtn.className = "card-action-btn";
                regenBtn.textContent = "Regen";
                regenBtn.addEventListener("click", async () => {
                    regenBtn.disabled = true;
                    regenBtn.textContent = "...";
                    await regenerateImage(img.image_id);
                });

                const delBtn = document.createElement("button");
                delBtn.className = "card-action-btn delete-btn";
                delBtn.textContent = "Del";
                delBtn.addEventListener("click", async () => {
                    if (confirm(`Delete image '${img.image_id}'?`)) {
                        await deleteImage(img.image_id);
                    }
                });

                actions.appendChild(viewBtn);
                actions.appendChild(regenBtn);
                actions.appendChild(delBtn);

                info.appendChild(promptElem);
                info.appendChild(meta);
                info.appendChild(actions);

                card.appendChild(thumbWrapper);
                card.appendChild(info);

                imagesGalleryContainer.appendChild(card);
            });

        } catch (err) {
            console.error("Failed to load images:", err);
            imagesGalleryContainer.innerHTML = `<div class="gallery-error">Failed to retrieve images: ${err.message}</div>`;
        }
    }

    function updateImageCounters(count) {
        if (modalImageCountBadge) modalImageCountBadge.textContent = `${count} IMAGES`;
        if (hudImageCountVal) hudImageCountVal.textContent = count;
    }

    // Direct Image Generation from Studio
    async function handleStudioGenerate() {
        const prompt = studioPromptInput.value.trim();
        if (!prompt || isGenerating) return;

        isGenerating = true;
        studioGenerateBtn.disabled = true;
        studioGenerateBtn.innerHTML = "<span>Generating...</span>";

        try {
            const res = await fetch("/api/images/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prompt })
            });

            const data = await res.json();
            if (!res.ok) {
                alert(data.error || "Image generation failed.");
                return;
            }

            studioPromptInput.value = "";
            await loadImages();

            // Open the freshly generated image in lightbox
            if (data.image) {
                openLightbox(data.image);
            }

        } catch (err) {
            alert(`Generation error: ${err.message}`);
        } finally {
            isGenerating = false;
            studioGenerateBtn.disabled = false;
            studioGenerateBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                </svg>
                <span>Generate</span>
            `;
        }
    }

    if (studioGenerateBtn) studioGenerateBtn.addEventListener("click", handleStudioGenerate);
    if (studioPromptInput) {
        studioPromptInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                handleStudioGenerate();
            }
        });
    }

    if (refreshImagesBtn) refreshImagesBtn.addEventListener("click", loadImages);

    // Regenerate Action
    async function regenerateImage(imageId) {
        try {
            const res = await fetch(`/api/images/${imageId}/regenerate`, { method: "POST" });
            const data = await res.json();
            if (!res.ok) {
                alert(data.error || "Regeneration failed.");
                return;
            }
            await loadImages();
            if (data.image) openLightbox(data.image);
        } catch (err) {
            alert(`Regeneration error: ${err.message}`);
        }
    }

    if (lightboxRegenBtn) {
        lightboxRegenBtn.addEventListener("click", async () => {
            if (!currentLightboxImage) return;
            lightboxRegenBtn.disabled = true;
            lightboxRegenBtn.textContent = "Regenerating...";
            await regenerateImage(currentLightboxImage.image_id);
            lightboxRegenBtn.disabled = false;
            lightboxRegenBtn.textContent = "Regenerate";
        });
    }

    // Delete Action
    async function deleteImage(imageId) {
        try {
            const res = await fetch(`/api/images/${imageId}`, { method: "DELETE" });
            if (!res.ok) throw new Error("Could not delete image.");
            if (currentLightboxImage && currentLightboxImage.image_id === imageId) {
                closeLightbox();
            }
            await loadImages();
        } catch (err) {
            alert(`Delete failed: ${err.message}`);
        }
    }

    if (lightboxDeleteBtn) {
        lightboxDeleteBtn.addEventListener("click", async () => {
            if (!currentLightboxImage) return;
            if (confirm(`Delete image '${currentLightboxImage.image_id}'?`)) {
                await deleteImage(currentLightboxImage.image_id);
            }
        });
    }

    // Listen for global message events to update image count badge
    window.addEventListener("tonyMessageCompleted", async () => {
        try {
            const res = await fetch("/api/images/status");
            if (res.ok) {
                const status = await res.json();
                updateImageCounters(status.total_images || 0);
            }
        } catch (e) {}
    });

    // Initial counter load
    async function checkImageCount() {
        try {
            const res = await fetch("/api/images/status");
            if (res.ok) {
                const status = await res.json();
                updateImageCounters(status.total_images || 0);
            }
        } catch (e) {}
    }
    checkImageCount();
});
