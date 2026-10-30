"""
TONY AI Stage 11: Personal Knowledge & RAG Subsystem.
Exports knowledge manager, models, loaders, embeddings, retriever, and errors.
"""
from knowledge.models import (
    Document,
    Chunk,
    Citation,
    SearchResult,
    RAGResponse,
    DocumentStatus
)
from knowledge.errors import (
    KnowledgeError,
    UnsupportedFileError,
    FileTooLargeError,
    CorruptedDocumentError,
    DuplicateDocumentError,
    EmbeddingUnavailableError,
    VectorStoreError,
    KnowledgeSecurityError,
    DocumentNotFoundError
)
from knowledge.security import KnowledgeSecurityPolicy
from knowledge.loaders import DocumentLoaderFactory, ALL_SUPPORTED_EXTENSIONS
from knowledge.chunker import IntelligentChunker
from knowledge.embeddings import (
    BaseEmbeddingProvider,
    OllamaEmbeddingProvider,
    MockEmbeddingProvider,
    get_embedding_provider
)
from knowledge.storage import KnowledgeDatabase
from knowledge.vector_store import VectorStore
from knowledge.keyword_search import KeywordSearchEngine
from knowledge.hybrid_search import HybridSearchEngine
from knowledge.citations import CitationManager
from knowledge.retriever import KnowledgeRetriever
from knowledge.manager import KnowledgeManager

__all__ = [
    "Document",
    "Chunk",
    "Citation",
    "SearchResult",
    "RAGResponse",
    "DocumentStatus",
    "KnowledgeError",
    "UnsupportedFileError",
    "FileTooLargeError",
    "CorruptedDocumentError",
    "DuplicateDocumentError",
    "EmbeddingUnavailableError",
    "VectorStoreError",
    "KnowledgeSecurityError",
    "DocumentNotFoundError",
    "KnowledgeSecurityPolicy",
    "DocumentLoaderFactory",
    "ALL_SUPPORTED_EXTENSIONS",
    "IntelligentChunker",
    "BaseEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "MockEmbeddingProvider",
    "get_embedding_provider",
    "KnowledgeDatabase",
    "VectorStore",
    "KeywordSearchEngine",
    "HybridSearchEngine",
    "CitationManager",
    "KnowledgeRetriever",
    "KnowledgeManager"
]
