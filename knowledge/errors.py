"""
Custom Exceptions for TONY AI Personal Knowledge & RAG Subsystem (Stage 11).
Provides descriptive, typed exceptions for ingestion, chunking, indexing,
embedding, search, and security policy enforcement.
"""

class KnowledgeError(Exception):
    """Base exception for all knowledge and RAG operations."""
    pass


class UnsupportedFileError(KnowledgeError):
    """Raised when an ingested file has an unsupported extension or MIME type."""
    pass


class FileTooLargeError(KnowledgeError):
    """Raised when an ingested file exceeds the configured maximum size limit."""
    pass


class CorruptedDocumentError(KnowledgeError):
    """Raised when a file cannot be parsed or read due to format corruption."""
    pass


class DuplicateDocumentError(KnowledgeError):
    """Raised when an identical document (by SHA-256 hash) has already been indexed."""
    pass


class EmbeddingUnavailableError(KnowledgeError):
    """Raised when the configured embedding provider or model is offline or unavailable."""
    pass


class VectorStoreError(KnowledgeError):
    """Raised when a vector store indexing or query operation encounters a database error."""
    pass


class KnowledgeSecurityError(KnowledgeError):
    """Raised when an ingestion or search operation violates security or sandboxing policies."""
    pass


class DocumentNotFoundError(KnowledgeError):
    """Raised when a requested document ID does not exist in the knowledge index."""
    pass
