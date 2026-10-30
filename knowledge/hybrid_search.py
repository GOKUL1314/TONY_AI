"""
Hybrid Ranking and Multi-Modal Retrieval Engine for TONY AI (Stage 11).
Combines dense semantic vector search with sparse BM25 keyword matching
into a unified, transparently weighted ranking pipeline with source attribution.
"""
import logging
from typing import List, Optional, Dict, Any

from knowledge.models import Chunk, Document, SearchResult, Citation
from knowledge.storage import KnowledgeDatabase
from knowledge.vector_store import VectorStore
from knowledge.keyword_search import KeywordSearchEngine
from knowledge.embeddings import BaseEmbeddingProvider
from knowledge.citations import CitationManager

logger = logging.getLogger("tony.knowledge.hybrid_search")


class HybridSearchEngine:
    """Orchestrates combined semantic and keyword search with transparent score fusion."""

    def __init__(
        self,
        db: Optional[KnowledgeDatabase] = None,
        vector_store: Optional[VectorStore] = None,
        keyword_search: Optional[KeywordSearchEngine] = None,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        semantic_weight: float = 0.65,
        keyword_weight: float = 0.35,
        vector_weight: Optional[float] = None
    ):
        self.vector_store = vector_store
        self.keyword_search = keyword_search
        self.db = db or (vector_store.db if vector_store else (keyword_search.db if keyword_search else None))
        self.embedding_provider = embedding_provider or (getattr(vector_store, "embedding_provider", None) if vector_store else None)
        self.semantic_weight = vector_weight if vector_weight is not None else semantic_weight
        self.keyword_weight = keyword_weight

    def search(
        self,
        query: str,
        top_k: int = 5,
        document_id: Optional[str] = None,
        file_type: Optional[str] = None,
        min_score: float = 0.0,
        **kwargs
    ) -> List[SearchResult]:
        """
        Execute hybrid search over knowledge base.
        Returns top_k SearchResult objects with citations.
        """
        if not query or not query.strip():
            return []

        clean_query = query.strip()

        # 1. Semantic Vector Retrieval
        sem_map: Dict[str, Tuple[Chunk, float]] = {}
        embeddings_active = False
        try:
            if self.embedding_provider.is_available():
                q_vec = self.embedding_provider.embed_text(clean_query)
                if q_vec:
                    sem_results = self.vector_store.search_semantic(
                        q_vec,
                        top_k=top_k * 3,
                        document_id=document_id
                    )
                    for chk, score in sem_results:
                        sem_map[chk.chunk_id] = (chk, score)
                    embeddings_active = True
        except Exception as e:
            logger.debug(f"Semantic search skipped or unavailable: {e}")

        # 2. Keyword BM25 Retrieval
        kw_map: Dict[str, Tuple[Chunk, float]] = {}
        try:
            kw_results = self.keyword_search.search_keywords(
                clean_query,
                top_k=top_k * 3,
                document_id=document_id
            )
            for chk, score in kw_results:
                kw_map[chk.chunk_id] = (chk, score)
        except Exception as e:
            logger.debug(f"Keyword search error: {e}")

        # 3. Score Fusion & Ranking
        all_chunk_ids = set(sem_map.keys()) | set(kw_map.keys())
        if not all_chunk_ids:
            return []

        # Adjust weights if embeddings are inactive
        w_sem = self.semantic_weight if embeddings_active else 0.0
        w_kw = self.keyword_weight if embeddings_active else 1.0
        weight_sum = (w_sem + w_kw) or 1.0
        w_sem /= weight_sum
        w_kw /= weight_sum

        fused_items = []
        doc_cache: Dict[str, Optional[Document]] = {}

        for cid in all_chunk_ids:
            chk = None
            s_score = 0.0
            k_score = 0.0

            if cid in sem_map:
                chk, s_score = sem_map[cid]
            if cid in kw_map:
                chk_kw, k_score = kw_map[cid]
                chk = chk or chk_kw

            if not chk:
                continue

            # Check document filter
            if document_id and chk.document_id != document_id:
                continue

            if chk.document_id not in doc_cache:
                doc_cache[chk.document_id] = self.db.get_document(chk.document_id)
            doc = doc_cache[chk.document_id]
            if not doc:
                continue

            # Check file type filter
            if file_type and doc.file_type.lower() != file_type.lower():
                continue

            # Formula: (w_sem * semantic) + (w_kw * keyword)
            final_score = (w_sem * s_score) + (w_kw * k_score)
            if final_score <= 0.0 or final_score < min_score:
                continue
            fused_items.append((chk, doc, final_score, s_score, k_score))

        # Sort descending by fused score
        fused_items.sort(key=lambda x: x[2], reverse=True)
        top_items = fused_items[:top_k]

        results: List[SearchResult] = []
        for idx, (chk, doc, score, sem_score, kw_score) in enumerate(top_items):
            citation = CitationManager.create_citation(
                index=idx + 1,
                chunk=chk,
                document=doc
            )
            results.append(SearchResult(
                chunk=chk,
                document=doc,
                score=score,
                semantic_score=sem_score,
                keyword_score=kw_score,
                citation=citation
            ))

        return results
