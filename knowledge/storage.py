"""
SQLite Storage and FTS5 Index Engine for TONY AI Personal Knowledge Subsystem (Stage 11).
Maintains relational tables for documents, chunks, binary vector BLOBs, and full-text FTS5 index.
"""
from contextlib import contextmanager
import json
import logging
from pathlib import Path
import re
import sqlite3
import struct
import threading
from typing import List, Optional, Dict, Any, Tuple

from knowledge.models import Document, Chunk, DocumentStatus
from knowledge.errors import VectorStoreError

logger = logging.getLogger("tony.knowledge.storage")

_local = threading.local()


class KnowledgeDatabase:
    """Manages persistent SQLite schema, FTS5 virtual table, and transactions for Knowledge/RAG."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create thread-local SQLite connection."""
        connections = getattr(_local, "knowledge_connections", None)
        if connections is None:
            connections = {}
            _local.knowledge_connections = connections

        path_key = str(self.db_path)
        conn = connections.get(path_key)
        if conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=15.0,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            # Enable Foreign Keys
            conn.execute("PRAGMA foreign_keys = ON;")
            connections[path_key] = conn
        return conn

    @contextmanager
    def get_cursor(self):
        """Context manager yielding a cursor with automatic commit/rollback."""
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def _init_schema(self) -> None:
        """Initialize document, chunk, and FTS5 full-text tables."""
        with self.get_cursor() as cur:
            # 1. Documents Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    sha256_hash TEXT NOT NULL UNIQUE,
                    original_path TEXT,
                    created_at TEXT NOT NULL,
                    ingestion_timestamp TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    embedding_status TEXT NOT NULL DEFAULT 'pending',
                    indexing_status TEXT NOT NULL DEFAULT 'pending',
                    status TEXT NOT NULL DEFAULT 'DISCOVERED',
                    error_message TEXT,
                    metadata_json TEXT
                );
            """)

            # 2. Chunks Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    page_number INTEGER,
                    section_header TEXT,
                    metadata_json TEXT,
                    embedding_blob BLOB,
                    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
                );
            """)

            # Indices on document_id and chunk_index
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks (document_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_index ON chunks (document_id, chunk_index);")

            # 3. FTS5 Virtual Table for BM25 Keyword Search
            try:
                cur.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                        chunk_id UNINDEXED,
                        document_id UNINDEXED,
                        filename,
                        section_header,
                        text
                    );
                """)
            except Exception as e:
                logger.warning(f"Could not initialize FTS5 virtual table: {e}")

    # =========================================================================
    # Document Operations
    # =========================================================================

    def save_document(self, doc: Document) -> None:
        """Insert or update a Document entity."""
        with self.get_cursor() as cur:
            cur.execute("""
                INSERT INTO documents (
                    id, filename, file_type, file_size, sha256_hash,
                    original_path, created_at, ingestion_timestamp, chunk_count,
                    embedding_status, indexing_status, status, error_message, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    filename=excluded.filename,
                    file_type=excluded.file_type,
                    file_size=excluded.file_size,
                    chunk_count=excluded.chunk_count,
                    embedding_status=excluded.embedding_status,
                    indexing_status=excluded.indexing_status,
                    status=excluded.status,
                    error_message=excluded.error_message,
                    metadata_json=excluded.metadata_json;
            """, (
                doc.document_id,
                doc.filename,
                doc.file_type,
                doc.file_size,
                doc.sha256_hash,
                doc.original_path,
                doc.created_at,
                doc.ingestion_timestamp,
                doc.chunk_count,
                doc.embedding_status,
                doc.indexing_status,
                doc.status.value if isinstance(doc.status, DocumentStatus) else str(doc.status),
                doc.error_message,
                json.dumps(doc.metadata or {})
            ))

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Fetch document by document_id."""
        with self.get_cursor() as cur:
            cur.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
            row = cur.fetchone()
            if row:
                return self._row_to_document(row)
        return None

    def find_document_by_hash(self, sha256_hash: str) -> Optional[Document]:
        """Fetch document by exact content hash."""
        with self.get_cursor() as cur:
            cur.execute("SELECT * FROM documents WHERE sha256_hash = ?", (sha256_hash,))
            row = cur.fetchone()
            if row:
                return self._row_to_document(row)
        return None

    def list_documents(self, limit: int = 200) -> List[Document]:
        """List all indexed documents, most recently ingested first."""
        with self.get_cursor() as cur:
            cur.execute("SELECT * FROM documents ORDER BY ingestion_timestamp DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            return [self._row_to_document(r) for r in rows]

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document, its chunks, and associated FTS index entries."""
        with self.get_cursor() as cur:
            cur.execute("DELETE FROM chunks_fts WHERE document_id = ?", (doc_id,))
            cur.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            cur.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return cur.rowcount > 0

    # =========================================================================
    # Chunk Operations
    # =========================================================================

    def save_chunks(self, chunks: List[Chunk], filename: str = "") -> None:
        """Bulk insert chunks and update full-text FTS index."""
        if not chunks:
            return

        with self.get_cursor() as cur:
            for chk in chunks:
                blob = None
                if chk.embedding is not None and len(chk.embedding) > 0:
                    blob = struct.pack(f"{len(chk.embedding)}f", *chk.embedding)

                cur.execute("""
                    INSERT OR REPLACE INTO chunks (
                        id, document_id, chunk_index, text, page_number,
                        section_header, metadata_json, embedding_blob
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    chk.chunk_id,
                    chk.document_id,
                    chk.chunk_index,
                    chk.text,
                    chk.page_number,
                    chk.section_header,
                    json.dumps(chk.metadata or {}),
                    blob
                ))

                # Insert into FTS5
                cur.execute("""
                    INSERT INTO chunks_fts (
                        chunk_id, document_id, filename, section_header, text
                    ) VALUES (?, ?, ?, ?, ?);
                """, (
                    chk.chunk_id,
                    chk.document_id,
                    filename,
                    chk.section_header or "",
                    chk.text
                ))

    def get_chunks(self, doc_id: str) -> List[Chunk]:
        """Fetch all chunks for a document ordered by chunk_index."""
        with self.get_cursor() as cur:
            cur.execute("SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index ASC", (doc_id,))
            rows = cur.fetchall()
            return [self._row_to_chunk(r) for r in rows]

    def search_fts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search full-text index directly."""
        clean = re.sub(r"[^\w\s]", " ", query).strip()
        if not clean:
            return []
        tokens = [f'"{t}"' for t in clean.split() if t]
        fts_q = " OR ".join(tokens)
        with self.get_cursor() as cur:
            try:
                cur.execute(
                    "SELECT chunk_id, document_id, filename, section_header, text FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT ?",
                    (fts_q, limit)
                )
                rows = cur.fetchall()
                return [{"chunk_id": r["chunk_id"], "document_id": r["document_id"], "filename": r["filename"], "text": r["text"]} for r in rows]
            except Exception as e:
                logger.warning(f"FTS search error: {e}")
                return []

    # Compatibility Aliases
    insert_document = save_document
    insert_chunks = save_chunks
    get_chunks_by_document = get_chunks

    def get_all_chunks_with_embeddings(self) -> List[Chunk]:
        """Fetch all chunks that possess embedding vectors."""
        with self.get_cursor() as cur:
            cur.execute("SELECT * FROM chunks WHERE embedding_blob IS NOT NULL;")
            rows = cur.fetchall()
            return [self._row_to_chunk(r) for r in rows]

    def get_stats(self) -> Dict[str, Any]:
        """Return summary metrics for the knowledge base."""
        with self.get_cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents;")
            doc_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM chunks;")
            chunk_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM chunks WHERE embedding_blob IS NOT NULL;")
            embedded_chunks = cur.fetchone()[0]

            cur.execute("SELECT SUM(file_size) FROM documents;")
            total_bytes = cur.fetchone()[0] or 0

        return {
            "total_documents": doc_count,
            "total_chunks": chunk_count,
            "embedded_chunks": embedded_chunks,
            "total_size_bytes": total_bytes,
            "total_size_mb": round(total_bytes / (1024 * 1024), 2)
        }

    # =========================================================================
    # Row Converters
    # =========================================================================

    def _row_to_document(self, row: sqlite3.Row) -> Document:
        meta = {}
        try:
            if row["metadata_json"]:
                meta = json.loads(row["metadata_json"])
        except Exception:
            pass

        return Document(
            document_id=row["id"],
            filename=row["filename"],
            file_type=row["file_type"],
            file_size=row["file_size"],
            sha256_hash=row["sha256_hash"],
            original_path=row["original_path"] or "",
            created_at=row["created_at"],
            ingestion_timestamp=row["ingestion_timestamp"],
            chunk_count=row["chunk_count"],
            embedding_status=row["embedding_status"],
            indexing_status=row["indexing_status"],
            status=DocumentStatus(row["status"]) if row["status"] in DocumentStatus.__members__ else DocumentStatus.READY,
            error_message=row["error_message"],
            metadata=meta
        )

    def _row_to_chunk(self, row: sqlite3.Row) -> Chunk:
        meta = {}
        try:
            if row["metadata_json"]:
                meta = json.loads(row["metadata_json"])
        except Exception:
            pass

        vec = None
        blob = row["embedding_blob"]
        if blob:
            try:
                num_floats = len(blob) // 4
                vec = list(struct.unpack(f"{num_floats}f", blob))
            except Exception:
                vec = None

        return Chunk(
            chunk_id=row["id"],
            document_id=row["document_id"],
            chunk_index=row["chunk_index"],
            text=row["text"],
            page_number=row["page_number"],
            section_header=row["section_header"],
            metadata=meta,
            embedding=vec
        )
