"""
Knowledge Base Lifecycle Manager for TONY AI (Stage 11).
Coordinates document ingestion, validation, hashing, chunking, embedding, indexing,
hybrid retrieval, verifiable RAG synthesis, and file sandboxing.
"""
from datetime import datetime
import hashlib
import logging
import os
from pathlib import Path
import shutil
from typing import List, Optional, Dict, Any

from knowledge.models import Document, Chunk, DocumentStatus, SearchResult, RAGResponse
from knowledge.errors import (
    KnowledgeError,
    UnsupportedFileError,
    FileTooLargeError,
    DuplicateDocumentError,
    DocumentNotFoundError,
    KnowledgeSecurityError,
    CorruptedDocumentError
)
from knowledge.security import KnowledgeSecurityPolicy
from knowledge.loaders import DocumentLoaderFactory, ALL_SUPPORTED_EXTENSIONS
from knowledge.chunker import IntelligentChunker
from knowledge.embeddings import BaseEmbeddingProvider, get_embedding_provider
from knowledge.storage import KnowledgeDatabase
from knowledge.vector_store import VectorStore
from knowledge.keyword_search import KeywordSearchEngine
from knowledge.hybrid_search import HybridSearchEngine
from knowledge.retriever import KnowledgeRetriever

logger = logging.getLogger("tony.knowledge.manager")


class KnowledgeManager:
    """Central orchestrator for Stage 11 Personal Knowledge & RAG system."""

    def __init__(
        self,
        storage_dir: Path | str,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        ai_provider = None,
        max_file_size_mb: int = 25,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        semantic_weight: float = 0.65,
        keyword_weight: float = 0.35
    ):
        self.storage_dir = Path(storage_dir)
        self.documents_dir = self.storage_dir / "documents"
        self.uploads_dir = self.storage_dir / "uploads"
        self.index_dir = self.storage_dir / "index"

        for d in [self.storage_dir, self.documents_dir, self.uploads_dir, self.index_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.db = KnowledgeDatabase(self.index_dir / "knowledge.db")
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.embedding_provider = embedding_provider or get_embedding_provider(None)
        self.ai_provider = ai_provider

        self.chunker = IntelligentChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.vector_store = VectorStore(self.db)
        self.keyword_search = KeywordSearchEngine(self.db)
        self.hybrid_search = HybridSearchEngine(
            db=self.db,
            vector_store=self.vector_store,
            keyword_search=self.keyword_search,
            embedding_provider=self.embedding_provider,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight
        )
        self.retriever = KnowledgeRetriever(
            hybrid_search=self.hybrid_search,
            ai_provider=self.ai_provider
        )

    @property
    def storage(self) -> KnowledgeDatabase:
        """Alias for underlying knowledge database storage."""
        return self.db

    # =========================================================================
    # Ingestion Pipeline
    # =========================================================================

    def ingest_file(
        self,
        file_path: Path | str,
        original_filename: Optional[str] = None
    ) -> Document:
        """
        Ingest a file into the knowledge base:
        1. Validate path and sandboxing.
        2. Validate size and extension.
        3. Compute SHA-256 and detect duplicates.
        4. Extract text preserving structure.
        5. Chunk intelligently.
        6. Compute embeddings (if provider is available).
        7. Index into SQLite and FTS5.
        """
        # 1. Path Safety & Validation
        validated_path = KnowledgeSecurityPolicy.validate_ingestion_path(file_path)
        if not validated_path.exists() or not validated_path.is_file():
            raise KnowledgeError(f"Target file does not exist: '{validated_path}'")

        # 2. Size Check
        file_size = validated_path.stat().st_size
        if file_size > self.max_file_size_bytes:
            raise FileTooLargeError(
                f"File size ({file_size / (1024*1024):.2f} MB) exceeds maximum allowed limit ({self.max_file_size_bytes / (1024*1024):.0f} MB)."
            )

        # 3. Extension Support Check
        fname = original_filename or validated_path.name
        ext = validated_path.suffix.lower()
        if ext not in ALL_SUPPORTED_EXTENSIONS:
            raise UnsupportedFileError(
                f"Unsupported document format '{ext}'. Cannot ingest '{fname}'."
            )

        # 4. Hashing & Duplicate Detection
        sha256 = self._compute_sha256(validated_path)
        existing = self.db.find_document_by_hash(sha256)
        if existing:
            logger.info(f"Duplicate document detected (hash: {sha256[:12]}): '{existing.filename}' ({existing.document_id})")
            raise DuplicateDocumentError(
                f"Document '{existing.filename}' with identical content is already indexed ({existing.document_id})."
            )

        # 5. Copy file to managed documents sandbox
        doc_id = f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{sha256[:8]}"
        dest_path = self.documents_dir / f"{doc_id}_{fname}"
        shutil.copy2(validated_path, dest_path)

        doc = Document(
            document_id=doc_id,
            filename=fname,
            file_type=ext,
            file_size=file_size,
            sha256_hash=sha256,
            original_path=str(dest_path),
            status=DocumentStatus.LOADING
        )
        self.db.save_document(doc)

        try:
            # 6. Load & Parse Document
            loader = DocumentLoaderFactory.get_loader(dest_path)
            loaded_units = loader.load(dest_path)

            # 7. Chunk Text
            doc.status = DocumentStatus.CHUNKING
            self.db.save_document(doc)
            chunks = self.chunker.chunk_document(
                document_id=doc_id,
                file_type=ext,
                loaded_units=loaded_units
            )
            doc.chunk_count = len(chunks)

            # 8. Compute Embeddings
            doc.status = DocumentStatus.EMBEDDING
            self.db.save_document(doc)

            if self.embedding_provider.is_available():
                for chk in chunks:
                    try:
                        chk.embedding = self.embedding_provider.embed_text(chk.text)
                    except Exception as emb_err:
                        logger.warning(f"Error embedding chunk '{chk.chunk_id}': {emb_err}")
                        chk.embedding = None
                doc.embedding_status = "completed"
            else:
                doc.embedding_status = "unavailable"

            # 9. Save Chunks & FTS5 Indexing
            doc.status = DocumentStatus.INDEXING
            self.db.save_document(doc)
            self.db.save_chunks(chunks, filename=fname)

            # 10. Mark Ready
            doc.indexing_status = "completed"
            doc.status = DocumentStatus.READY
            self.db.save_document(doc)
            logger.info(f"Successfully ingested '{fname}' ({doc_id}) with {len(chunks)} chunks.")
            return doc

        except Exception as e:
            logger.error(f"Error during ingestion pipeline for '{fname}': {e}")
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(e)
            self.db.save_document(doc)
            raise

    def ingest_bytes(self, content_bytes: bytes, filename: str) -> Document:
        """Staging helper to ingest in-memory uploaded file bytes."""
        if not filename or not filename.strip():
            raise KnowledgeError("Filename cannot be empty.")

        clean_name = Path(filename).name.strip()
        KnowledgeSecurityPolicy.validate_ingestion_path(clean_name)

        if len(content_bytes) > self.max_file_size_bytes:
            raise FileTooLargeError(f"Uploaded file exceeds maximum limit of {self.max_file_size_bytes // (1024*1024)} MB.")

        temp_path = self.uploads_dir / clean_name
        try:
            temp_path.write_bytes(content_bytes)
            return self.ingest_file(temp_path, original_filename=clean_name)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    # =========================================================================
    # Search & RAG
    # =========================================================================

    def search(
        self,
        query: str,
        top_k: int = 5,
        document_id: Optional[str] = None,
        file_type: Optional[str] = None,
        min_score: float = 0.0,
        **kwargs
    ) -> List[SearchResult]:
        """Search the knowledge base using hybrid fusion."""
        return self.hybrid_search.search(
            query=query,
            top_k=top_k,
            document_id=document_id,
            file_type=file_type,
            min_score=min_score,
            **kwargs
        )

    def ask(
        self,
        question: str,
        top_k: int = 5,
        document_id: Optional[str] = None,
        ai_provider=None
    ) -> RAGResponse:
        """Answer a user question grounded in retrieved knowledge."""
        return self.retriever.answer(
            question=question,
            top_k=top_k,
            document_id=document_id,
            ai_provider=ai_provider or self.ai_provider
        )

    # =========================================================================
    # Document Management
    # =========================================================================

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Fetch document metadata by document_id."""
        return self.db.get_document(doc_id)

    def list_documents(self) -> List[Document]:
        """List all indexed documents."""
        return self.db.list_documents()

    def delete_document(self, doc_id: str) -> bool:
        """Delete document and remove physical file from storage."""
        doc = self.db.get_document(doc_id)
        if not doc:
            raise DocumentNotFoundError(f"Document '{doc_id}' not found.")

        # Remove physical file if in managed documents_dir
        if doc.original_path:
            p = Path(doc.original_path)
            if p.exists() and p.is_file() and self.documents_dir in p.parents:
                try:
                    p.unlink()
                except Exception as e:
                    logger.warning(f"Could not delete physical file for doc '{doc_id}': {e}")

        success = self.db.delete_document(doc_id)
        logger.info(f"Deleted document '{doc_id}' (success={success}).")
        return success

    def reindex_document(self, doc_id: str) -> Document:
        """Re-parse, re-chunk, and re-embed an existing document."""
        doc = self.db.get_document(doc_id)
        if not doc:
            raise DocumentNotFoundError(f"Document '{doc_id}' not found.")

        if not doc.original_path or not Path(doc.original_path).exists():
            raise CorruptedDocumentError(f"Original source file for '{doc_id}' is no longer accessible on disk.")

        src_path = Path(doc.original_path)

        # Remove existing chunks and FTS
        with self.db.get_cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            cur.execute("DELETE FROM chunks_fts WHERE document_id = ?", (doc_id,))

        loader = DocumentLoaderFactory.get_loader(src_path)
        loaded_units = loader.load(src_path)
        chunks = self.chunker.chunk_document(
            document_id=doc_id,
            file_type=doc.file_type,
            loaded_units=loaded_units
        )
        doc.chunk_count = len(chunks)

        if self.embedding_provider.is_available():
            for chk in chunks:
                try:
                    chk.embedding = self.embedding_provider.embed_text(chk.text)
                except Exception:
                    chk.embedding = None
            doc.embedding_status = "completed"
        else:
            doc.embedding_status = "unavailable"

        self.db.save_chunks(chunks, filename=doc.filename)
        doc.status = DocumentStatus.READY
        self.db.save_document(doc)
        logger.info(f"Re-indexed document '{doc_id}' with {len(chunks)} chunks.")
        return doc

    def reindex_all(self) -> Dict[str, Any]:
        """Reindex all indexed documents."""
        docs = self.list_documents()
        successes = 0
        failures = 0
        errors = []

        for d in docs:
            try:
                self.reindex_document(d.document_id)
                successes += 1
            except Exception as e:
                failures += 1
                errors.append(f"{d.filename}: {str(e)}")

        return {
            "total": len(docs),
            "reindexed": successes,
            "failed": failures,
            "errors": errors
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return metrics and statistics about the knowledge base."""
        stats = self.db.get_stats()
        stats["embedding_provider"] = self.embedding_provider.provider_name
        stats["embedding_model"] = self.embedding_provider.model_name
        stats["embedding_available"] = self.embedding_provider.is_available()
        return stats

    def check_health(self) -> Dict[str, Any]:
        """Check availability of storage and embedding components."""
        db_healthy = True
        try:
            with self.db.get_cursor() as cur:
                cur.execute("SELECT 1;")
        except Exception:
            db_healthy = False

        emb_avail = self.embedding_provider.is_available()

        return {
            "status": "healthy" if db_healthy else "degraded",
            "healthy": db_healthy,
            "database": "connected" if db_healthy else "error",
            "embedding_provider": self.embedding_provider.provider_name,
            "embedding_model": self.embedding_provider.model_name,
            "embeddings_ready": emb_avail,
            "storage_dir": str(self.storage_dir)
        }

    # =========================================================================
    # Helpers
    # =========================================================================

    def _compute_sha256(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of a file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
