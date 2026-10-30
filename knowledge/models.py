"""
Data Models for TONY AI Personal Knowledge & RAG Subsystem (Stage 11).
Defines structured classes for documents, chunks, citations, search results, and RAG responses.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional


class DocumentStatus(str, Enum):
    """Lifecycle statuses for ingested knowledge documents."""
    DISCOVERED = "DISCOVERED"
    LOADING = "LOADING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    READY = "READY"
    INDEXED = "READY"
    FAILED = "FAILED"


@dataclass
class Document:
    """Represents an ingested document in the knowledge base."""
    document_id: str
    filename: str
    file_type: str
    file_size: int
    sha256_hash: str
    original_path: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    ingestion_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    chunk_count: int = 0
    embedding_status: str = "pending"
    indexing_status: str = "pending"
    status: DocumentStatus = DocumentStatus.DISCOVERED
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.document_id

    @property
    def format(self) -> str:
        return self.file_type

    @property
    def file_size_bytes(self) -> int:
        return self.file_size

    @property
    def sha256(self) -> str:
        return self.sha256_hash


    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.document_id,
            "document_id": self.document_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "format": self.file_type,
            "file_size": self.file_size,
            "file_size_bytes": self.file_size,
            "sha256_hash": self.sha256_hash,
            "original_path": self.original_path,
            "created_at": self.created_at,
            "ingestion_timestamp": self.ingestion_timestamp,
            "chunk_count": self.chunk_count,
            "embedding_status": self.embedding_status,
            "indexing_status": self.indexing_status,
            "status": self.status.value if isinstance(self.status, DocumentStatus) else str(self.status),
            "error_message": self.error_message,
            "metadata": self.metadata
        }


@dataclass
class Chunk:
    """Represents a discrete semantic chunk of a document."""
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    page_number: Optional[int] = None
    section_header: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None

    @property
    def section_title(self) -> Optional[str]:
        return self.section_header

    @property
    def total_chunks(self) -> int:
        return self.metadata.get("total_chunks", 1)

    def to_dict(self, include_embedding: bool = False) -> Dict[str, Any]:
        d = {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "page_number": self.page_number,
            "section_header": self.section_header,
            "section_title": self.section_header,
            "total_chunks": self.total_chunks,
            "metadata": self.metadata
        }
        if include_embedding and self.embedding is not None:
            d["embedding"] = self.embedding
        return d


@dataclass
class Citation:
    """Source attribution for answers derived from knowledge retrieval."""
    citation_id: str = ""  # e.g., "[1]"
    filename: str = ""
    document_id: str = ""
    chunk_id: str = ""
    page_number: Optional[int] = None
    section_header: Optional[str] = None
    snippet: str = ""
    relevance_score: float = 0.0

    def __init__(
        self,
        citation_id: str = "",
        filename: str = "",
        document_id: str = "",
        chunk_id: str = "",
        page_number: Optional[int] = None,
        section_header: Optional[str] = None,
        snippet: str = "",
        relevance_score: float = 0.0,
        document_name: Optional[str] = None,
        section_title: Optional[str] = None,
        **kwargs
    ):
        self.citation_id = citation_id
        self.filename = filename or document_name or ""
        self.document_id = document_id
        self.chunk_id = chunk_id
        self.page_number = page_number
        self.section_header = section_header or section_title
        self.snippet = snippet
        self.relevance_score = relevance_score

    @property
    def document_name(self) -> str:
        return self.filename

    @property
    def section_title(self) -> Optional[str]:
        return self.section_header

    def to_dict(self) -> Dict[str, Any]:
        return {
            "citation_id": self.citation_id,
            "filename": self.filename,
            "document_name": self.filename,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "page_number": self.page_number,
            "section_header": self.section_header,
            "section_title": self.section_header,
            "snippet": self.snippet,
            "relevance_score": self.relevance_score
        }

    def format(self, index: Optional[int] = None) -> str:
        """Formatted human-readable citation label with optional index override."""
        cid = f"[{index}]" if index is not None else (self.citation_id or "[1]")
        loc = []
        if self.page_number is not None:
            loc.append(f"Page {self.page_number}")
        if self.section_header:
            loc.append(f"Section: {self.section_header}")
        loc_str = f" — {', '.join(loc)}" if loc else ""
        return f"{cid} {self.filename}{loc_str}"

    def format_text(self) -> str:
        """Formatted human-readable citation label."""
        return self.format()



@dataclass
class SearchResult:
    """Search match combining chunk, document metadata, and hybrid scores."""
    chunk: Chunk
    document: Document
    score: float
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    citation: Optional[Citation] = None

    @property
    def document_id(self) -> str:
        return self.document.document_id

    @property
    def document_name(self) -> str:
        return self.document.filename

    @property
    def filename(self) -> str:
        return self.document.filename

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    @property
    def text(self) -> str:
        return self.chunk.text

    @property
    def page_number(self) -> Optional[int]:
        return self.chunk.page_number

    @property
    def section_title(self) -> Optional[str]:
        return self.chunk.section_header

    @property
    def combined_score(self) -> float:
        return self.score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk": self.chunk.to_dict(),
            "document": self.document.to_dict(),
            "score": round(self.score, 4),
            "combined_score": round(self.score, 4),
            "document_name": self.document_name,
            "document_id": self.document_id,
            "text": self.text,
            "page_number": self.page_number,
            "section_title": self.section_title,
            "semantic_score": round(self.semantic_score, 4),
            "keyword_score": round(self.keyword_score, 4),
            "citation": self.citation.to_dict() if self.citation else None
        }


@dataclass
class RAGResponse:
    """Answer synthesized from retrieved knowledge chunks with source citations."""
    query: str
    answer: str
    citations: List[Citation] = field(default_factory=list)
    retrieved_chunks: List[SearchResult] = field(default_factory=list)
    duration_seconds: float = 0.0
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "retrieved_chunks": [r.to_dict() for r in self.retrieved_chunks],
            "duration_seconds": round(self.duration_seconds, 3),
            "confidence": round(self.confidence, 3)
        }
