/**
 * TONY AI Assistant - Stage 4 Long-Term Memory Client Controller
 * Manages the Memory Console modal, search queries, category filters,
 * manual memory deletion, and real-time HUD telemetry updates.
 */

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const openMemoryBtn = document.getElementById("openMemoryBtn");
    const closeMemoryBtn = document.getElementById("closeMemoryBtn");
    const memoryModalOverlay = document.getElementById("memoryModalOverlay");
    const memorySearchInput = document.getElementById("memorySearchInput");
    const memoryCategorySelect = document.getElementById("memoryCategorySelect");
    const refreshMemoryBtn = document.getElementById("refreshMemoryBtn");
    const clearAllMemoryBtn = document.getElementById("clearAllMemoryBtn");
    const memoryCardsContainer = document.getElementById("memoryCardsContainer");
    const hudMemoryCountVal = document.getElementById("hudMemoryCountVal");
    const modalMemoryCountBadge = document.getElementById("modalMemoryCountBadge");

    let searchDebounceTimeout = null;

    // Open / Close Modal
    function openMemoryModal() {
        memoryModalOverlay.classList.add("active");
        fetchMemories();
    }

    function closeMemoryModal() {
        memoryModalOverlay.classList.remove("active");
    }

    if (openMemoryBtn) openMemoryBtn.addEventListener("click", openMemoryModal);
    if (closeMemoryBtn) closeMemoryBtn.addEventListener("click", closeMemoryModal);

    memoryModalOverlay.addEventListener("click", (e) => {
        if (e.target === memoryModalOverlay) {
            closeMemoryModal();
        }
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && memoryModalOverlay.classList.contains("active")) {
            closeMemoryModal();
        }
    });

    // Format timestamps
    function formatDate(isoStr) {
        if (!isoStr) return "Never";
        try {
            const d = new Date(isoStr);
            return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
            return isoStr;
        }
    }

    // Render Importance Stars
    function renderImportanceStars(level) {
        const num = Math.max(1, Math.min(5, parseInt(level) || 2));
        return "★".repeat(num) + "☆".repeat(5 - num);
    }

    // Escape HTML
    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    // Update HUD and Modal Count Badges
    async function updateMemoryCount() {
        try {
            const res = await fetch("/api/memory/stats");
            if (res.ok) {
                const data = await res.json();
                const activeCount = data.stats ? data.stats.active_memories : 0;
                if (hudMemoryCountVal) hudMemoryCountVal.textContent = activeCount;
                if (modalMemoryCountBadge) modalMemoryCountBadge.textContent = `${activeCount} ITEMS`;
            }
        } catch (e) {
            console.debug("Failed to update memory count telemetry:", e);
        }
    }

    // Fetch and render memories
    async function fetchMemories() {
        const category = memoryCategorySelect ? memoryCategorySelect.value : "all";
        const query = memorySearchInput ? memorySearchInput.value.trim() : "";

        memoryCardsContainer.innerHTML = '<div class="memory-loading">Accessing memory database...</div>';

        try {
            let res;
            if (query) {
                res = await fetch("/api/memory/search", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ query: query })
                });
            } else {
                const url = category && category !== "all" 
                    ? `/api/memory?category=${encodeURIComponent(category)}`
                    : "/api/memory";
                res = await fetch(url);
            }

            const data = await res.json();
            if (!res.ok || !data.success) {
                memoryCardsContainer.innerHTML = `<div class="memory-error">Failed to load memories: ${data.error || 'Server error'}</div>`;
                return;
            }

            const memories = query ? data.results : data.memories;
            renderMemoryCards(memories || []);
            updateMemoryCount();

        } catch (err) {
            console.error("Fetch memories error:", err);
            memoryCardsContainer.innerHTML = `<div class="memory-error">Network error accessing memory database: ${err.message}</div>`;
        }
    }

    function renderMemoryCards(memories) {
        if (!memories || memories.length === 0) {
            memoryCardsContainer.innerHTML = `
                <div class="memory-empty-state">
                    <div class="empty-icon">📂</div>
                    <h3>No Memories Found</h3>
                    <p>TONY automatically remembers personal facts, preferences, and project context across restarts.<br>
                    Try telling TONY: <em>"Remember that my name is Gokul"</em> or <em>"Remember that I prefer Python"</em>.</p>
                </div>
            `;
            return;
        }

        memoryCardsContainer.innerHTML = "";
        memories.forEach(mem => {
            const card = document.createElement("div");
            card.className = "memory-card";
            card.id = `mem-card-${mem.id}`;

            const categoryClass = `cat-${(mem.category || 'other').toLowerCase()}`;
            const stars = renderImportanceStars(mem.importance);

            card.innerHTML = `
                <div class="memory-card-header">
                    <span class="memory-category-tag ${categoryClass}">[${escapeHtml(mem.category).toUpperCase()}]</span>
                    <span class="memory-importance" title="Priority level: ${mem.importance}/5">${stars}</span>
                </div>
                <div class="memory-card-body">
                    <div class="memory-key">${escapeHtml(mem.memory_key.replace(/_/g, " ").toUpperCase())}</div>
                    <div class="memory-value">${escapeHtml(mem.memory_value)}</div>
                </div>
                <div class="memory-card-footer">
                    <div class="memory-meta-info">
                        <span>Created: ${formatDate(mem.created_at)}</span>
                        <span>Uses: ${mem.access_count || 1}</span>
                    </div>
                    <button class="memory-delete-btn" data-id="${mem.id}" title="Delete memory">&times; Forget</button>
                </div>
            `;

            // Attach individual delete handler
            const delBtn = card.querySelector(".memory-delete-btn");
            delBtn.addEventListener("click", () => deleteMemory(mem.id));

            memoryCardsContainer.appendChild(card);
        });
    }

    // Delete single memory
    async function deleteMemory(id) {
        if (!confirm(`Are you sure you want to forget this memory?`)) return;

        try {
            const res = await fetch(`/api/memory/${id}`, { method: "DELETE" });
            const data = await res.json();
            if (res.ok && data.success) {
                const card = document.getElementById(`mem-card-${id}`);
                if (card) {
                    card.style.opacity = "0";
                    card.style.transform = "scale(0.95)";
                    setTimeout(() => card.remove(), 200);
                }
                updateMemoryCount();
            } else {
                alert(`Error: ${data.error || 'Could not delete memory'}`);
            }
        } catch (e) {
            alert(`Network error: ${e.message}`);
        }
    }

    // Clear all memories
    async function clearAllMemories() {
        if (!confirm("Are you sure you want to delete ALL stored memories? This cannot be undone.")) return;

        try {
            const res = await fetch("/api/memory", { method: "DELETE" });
            const data = await res.json();
            if (res.ok && data.success) {
                fetchMemories();
                updateMemoryCount();
            } else {
                alert(`Error: ${data.error || 'Could not clear memories'}`);
            }
        } catch (e) {
            alert(`Network error: ${e.message}`);
        }
    }

    if (clearAllMemoryBtn) clearAllMemoryBtn.addEventListener("click", clearAllMemories);
    if (refreshMemoryBtn) refreshMemoryBtn.addEventListener("click", fetchMemories);

    if (memoryCategorySelect) {
        memoryCategorySelect.addEventListener("change", fetchMemories);
    }

    if (memorySearchInput) {
        memorySearchInput.addEventListener("input", () => {
            clearTimeout(searchDebounceTimeout);
            searchDebounceTimeout = setTimeout(fetchMemories, 250);
        });
    }

    // Global listener so chat or voice updates trigger count refresh
    window.addEventListener("tonyMessageCompleted", () => {
        updateMemoryCount();
    });

    // Initial count fetch on boot
    updateMemoryCount();
});
