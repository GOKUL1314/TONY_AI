/**
 * TONY AI - Personal Knowledge & RAG Studio Client Module (Stage 11)
 * Manages document ingestion, dropzone, structured search, grounded RAG querying,
 * citation display, and indexed documents management.
 */

class TonyKnowledgeStudio {
    constructor() {
        // Elements
        this.overlay = document.getElementById("knowledgeModalOverlay");
        this.openBtn = document.getElementById("openKnowledgeBtn");
        this.closeBtn = document.getElementById("closeKnowledgeModalBtn");
        this.dropZone = document.getElementById("knowledgeDropZone");
        this.fileInput = document.getElementById("knowledgeFileInput");
        this.uploadProgress = document.getElementById("knowledgeUploadProgress");
        this.uploadStatus = document.getElementById("knowledgeUploadStatus");
        this.queryInput = document.getElementById("knowledgeQueryInput");

        // Action Buttons
        this.btnAsk = document.getElementById("btnKnowledgeAsk");
        this.btnSearch = document.getElementById("btnKnowledgeSearch");
        this.btnRefresh = document.getElementById("btnRefreshKnowledge");

        // Telemetry
        this.statDocs = document.getElementById("kStatDocs");
        this.statChunks = document.getElementById("kStatChunks");
        this.statStorage = document.getElementById("kStatStorage");
        this.statIndex = document.getElementById("kStatIndex");

        // Status & Result
        this.errorBanner = document.getElementById("knowledgeErrorBanner");
        this.errorMessage = document.getElementById("knowledgeErrorMessage");
        this.resultShowcase = document.getElementById("knowledgeResultShowcase");
        this.resultTitle = document.getElementById("knowledgeResultTitle");
        this.resultMeta = document.getElementById("knowledgeResultMeta");
        this.resultBody = document.getElementById("knowledgeResultBody");
        this.citationsSection = document.getElementById("knowledgeCitationsSection");
        this.citationsList = document.getElementById("knowledgeCitationsList");
        this.documentsList = document.getElementById("knowledgeDocumentsList");

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
        if (this.btnRefresh) {
            this.btnRefresh.addEventListener("click", () => this.refreshAll());
        }

        // Dropzone interactions
        if (this.dropZone) {
            this.dropZone.addEventListener("click", () => {
                if (this.fileInput) this.fileInput.click();
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
                if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                    this.handleFiles(e.dataTransfer.files);
                }
            });
        }

        if (this.fileInput) {
            this.fileInput.addEventListener("change", (e) => {
                if (e.target.files && e.target.files.length > 0) {
                    this.handleFiles(e.target.files);
                }
            });
        }

        // Query execution
        if (this.btnAsk) {
            this.btnAsk.addEventListener("click", () => this.askQuestion());
        }
        if (this.btnSearch) {
            this.btnSearch.addEventListener("click", () => this.searchChunks());
        }
        if (this.queryInput) {
            this.queryInput.addEventListener("keydown", (e) => {
                if (e.key === "Enter") {
                    this.askQuestion();
                }
            });
        }

        // Global ESC key listener
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && this.overlay && this.overlay.style.display !== "none") {
                this.close();
            }
        });
    }

    open() {
        if (!this.overlay) return;
        this.overlay.style.display = "flex";
        this.hideError();
        this.refreshAll();
    }

    close() {
        if (!this.overlay) return;
        this.overlay.style.display = "none";
        this.hideError();
    }

    showError(msg) {
        if (this.errorBanner && this.errorMessage) {
            this.errorMessage.textContent = msg || "An error occurred";
            this.errorBanner.style.display = "flex";
        }
    }

    hideError() {
        if (this.errorBanner) {
            this.errorBanner.style.display = "none";
        }
    }

    async refreshAll() {
        await Promise.all([
            this.loadStats(),
            this.loadDocuments()
        ]);
    }

    async loadStats() {
        try {
            const resp = await fetch("/api/knowledge/stats");
            const data = await resp.json();
            if (data.status === "success" && data.stats) {
                const s = data.stats;
                if (this.statDocs) this.statDocs.textContent = s.total_documents || 0;
                if (this.statChunks) this.statChunks.textContent = s.total_chunks || 0;
                if (this.statStorage) {
                    const kb = Math.round((s.total_file_size_bytes || 0) / 1024);
                    this.statStorage.textContent = `${kb} KB`;
                }
                if (this.statIndex) {
                    this.statIndex.textContent = s.embedding_provider === "ollama" ? "Hybrid Vector+FTS5" : "SQLite FTS5 BM25";
                }
            }
        } catch (err) {
            console.error("Failed to load knowledge stats:", err);
        }
    }

    async loadDocuments() {
        if (!this.documentsList) return;
        try {
            const resp = await fetch("/api/knowledge/documents");
            const data = await resp.json();
            if (data.status === "success") {
                this.renderDocuments(data.documents || []);
            }
        } catch (err) {
            console.error("Failed to load documents:", err);
            this.showError("Failed to fetch documents list.");
        }
    }

    renderDocuments(docs) {
        if (!this.documentsList) return;
        if (!docs || docs.length === 0) {
            this.documentsList.innerHTML = `<div class="empty-state">No documents ingested yet. Drop files above to build your personal knowledge base.</div>`;
            return;
        }

        this.documentsList.innerHTML = "";
        docs.forEach(doc => {
            const card = document.createElement("div");
            card.className = "knowledge-doc-card";

            const kb = Math.round((doc.file_size_bytes || 0) / 1024);
            const dateStr = doc.created_at ? new Date(doc.created_at).toLocaleString() : "Unknown";

            card.innerHTML = `
                <div class="doc-card-header">
                    <span class="doc-badge doc-badge-${(doc.format || 'txt').toLowerCase()}">${(doc.format || 'TXT').toUpperCase()}</span>
                    <span class="doc-filename" title="${doc.filename}">${doc.filename}</span>
                    <button class="doc-delete-btn" data-doc-id="${doc.id}" title="Delete document and its chunks">&times;</button>
                </div>
                <div class="doc-card-body">
                    <div class="doc-meta-item"><span>Chunks:</span> <strong>${doc.chunk_count || 0}</strong></div>
                    <div class="doc-meta-item"><span>Size:</span> <strong>${kb} KB</strong></div>
                    <div class="doc-meta-item"><span>Indexed:</span> <strong>${dateStr}</strong></div>
                </div>
            `;

            // Delete event
            const delBtn = card.querySelector(".doc-delete-btn");
            if (delBtn) {
                delBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    this.deleteDocument(doc.id, doc.filename);
                });
            }

            this.documentsList.appendChild(card);
        });
    }

    async handleFiles(files) {
        if (!files || files.length === 0) return;
        this.hideError();

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            await this.uploadFile(file);
        }

        if (this.fileInput) this.fileInput.value = "";
        await this.refreshAll();
    }

    async uploadFile(file) {
        if (!file) return;

        if (this.uploadProgress) {
            this.uploadProgress.style.display = "flex";
            if (this.uploadStatus) this.uploadStatus.textContent = `Ingesting '${file.name}'...`;
        }

        const formData = new FormData();
        formData.append("file", file);

        try {
            const resp = await fetch("/api/knowledge/ingest", {
                method: "POST",
                body: formData
            });
            const data = await resp.json();

            if (!resp.ok) {
                this.showError(`Error ingesting '${file.name}': ${data.error || 'Upload failed'}`);
            } else {
                console.log(`Document '${file.name}' ingested:`, data);
            }
        } catch (err) {
            console.error(`Ingest error for '${file.name}':`, err);
            this.showError(`Failed to upload '${file.name}': Network error.`);
        } finally {
            if (this.uploadProgress) {
                this.uploadProgress.style.display = "none";
            }
        }
    }

    async deleteDocument(docId, filename) {
        if (!confirm(`Are you sure you want to delete '${filename}' from your knowledge base?`)) {
            return;
        }

        try {
            const resp = await fetch(`/api/knowledge/documents/${encodeURIComponent(docId)}`, {
                method: "DELETE"
            });
            const data = await resp.json();
            if (resp.ok && data.status === "success") {
                await this.refreshAll();
            } else {
                this.showError(`Failed to delete document: ${data.error || 'Server error'}`);
            }
        } catch (err) {
            console.error("Delete error:", err);
            this.showError("Network error while deleting document.");
        }
    }

    async askQuestion() {
        const query = this.queryInput ? this.queryInput.value.trim() : "";
        if (!query) {
            this.showError("Please enter a question or topic to search.");
            return;
        }

        this.hideError();
        this.setLoading("Searching knowledge base & synthesizing grounded response...");

        try {
            const resp = await fetch("/api/knowledge/ask", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question: query, top_k: 5 })
            });
            const data = await resp.json();

            if (!resp.ok) {
                this.showError(data.error || "Failed to answer question.");
                this.hideResult();
            } else {
                this.renderRAGAnswer(data);
            }
        } catch (err) {
            console.error("Ask error:", err);
            this.showError("Network error while querying knowledge base.");
            this.hideResult();
        } finally {
            this.clearLoading();
        }
    }

    async searchChunks() {
        const query = this.queryInput ? this.queryInput.value.trim() : "";
        if (!query) {
            this.showError("Please enter keywords or query to search chunks.");
            return;
        }

        this.hideError();
        this.setLoading("Retrieving relevant knowledge chunks...");

        try {
            const resp = await fetch("/api/knowledge/search", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query: query, top_k: 5 })
            });
            const data = await resp.json();

            if (!resp.ok) {
                this.showError(data.error || "Search failed.");
                this.hideResult();
            } else {
                this.renderSearchResults(data);
            }
        } catch (err) {
            console.error("Search error:", err);
            this.showError("Network error during chunk search.");
            this.hideResult();
        } finally {
            this.clearLoading();
        }
    }

    renderRAGAnswer(ragData) {
        if (!this.resultShowcase) return;
        this.resultShowcase.style.display = "block";
        if (this.resultTitle) this.resultTitle.textContent = "GROUNDED RAG ANSWER";
        if (this.resultMeta) {
            const conf = Math.round((ragData.confidence || 0) * 100);
            this.resultMeta.textContent = `Confidence: ${conf}% | ${ragData.search_mode || 'Hybrid'}`;
        }
        if (this.resultBody) {
            this.resultBody.textContent = ragData.answer || "No relevant information found.";
        }

        // Citations
        if (this.citationsSection && this.citationsList) {
            const citations = ragData.citations || [];
            if (citations.length > 0) {
                this.citationsSection.style.display = "block";
                this.citationsList.innerHTML = citations.map(c => `
                    <div class="citation-card">
                        <div class="citation-header">
                            <span class="citation-index">[${c.index}]</span>
                            <span class="citation-doc">${c.document_name}</span>
                            ${c.page_number ? `<span class="citation-page">Page ${c.page_number}</span>` : ''}
                            ${c.section_title ? `<span class="citation-sec">${c.section_title}</span>` : ''}
                        </div>
                        <div class="citation-snippet">"${c.snippet || ''}"</div>
                    </div>
                `).join("");
            } else {
                this.citationsSection.style.display = "none";
                this.citationsList.innerHTML = "";
            }
        }
    }

    renderSearchResults(searchData) {
        if (!this.resultShowcase) return;
        this.resultShowcase.style.display = "block";
        if (this.resultTitle) this.resultTitle.textContent = "RELEVANT CHUNKS";
        if (this.resultMeta) {
            this.resultMeta.textContent = `Found ${searchData.count || 0} chunks`;
        }

        const results = searchData.results || [];
        if (results.length === 0) {
            if (this.resultBody) this.resultBody.textContent = "No matching chunks found.";
            if (this.citationsSection) this.citationsSection.style.display = "none";
            return;
        }

        if (this.resultBody) {
            this.resultBody.innerHTML = results.map((r, i) => `
                <div class="search-chunk-card">
                    <div class="chunk-card-meta">
                        <span class="chunk-rank">#${i + 1}</span>
                        <strong>${r.document_name || 'Document'}</strong>
                        ${r.page_number ? `<span>Page ${r.page_number}</span>` : ''}
                        ${r.section_title ? `<span>${r.section_title}</span>` : ''}
                        <span class="chunk-score">Score: ${r.combined_score ? r.combined_score.toFixed(3) : '0.000'}</span>
                    </div>
                    <pre class="chunk-card-text">${r.text || ''}</pre>
                </div>
            `).join("");
        }
        if (this.citationsSection) this.citationsSection.style.display = "none";
    }

    hideResult() {
        if (this.resultShowcase) this.resultShowcase.style.display = "none";
    }

    setLoading(msg) {
        if (this.uploadProgress) {
            this.uploadProgress.style.display = "flex";
            if (this.uploadStatus) this.uploadStatus.textContent = msg;
        }
    }

    clearLoading() {
        if (this.uploadProgress) {
            this.uploadProgress.style.display = "none";
        }
    }
}

// Instantiate on DOM load
document.addEventListener("DOMContentLoaded", () => {
    window.tonyKnowledgeStudio = new TonyKnowledgeStudio();
});
