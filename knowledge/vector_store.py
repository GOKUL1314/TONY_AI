"""
Local Vector Store and Cosine Similarity Engine for TONY AI (Stage 11).
Computes normalized dot-product cosine similarity over stored chunk embeddings using NumPy.
"""
import logging
from typing import List, Tuple, Optional, Any
import numpy as np

from knowledge.models import Chunk
from knowledge.storage import KnowledgeDatabase

logger = logging.getLogger("tony.knowledge.vector_store")


class VectorStore:
    """Computes semantic similarity matches against stored document chunk vectors."""

    def __init__(
        self,
        db: Optional[KnowledgeDatabase] = None,
        storage: Optional[KnowledgeDatabase] = None,
        embedding_provider: Optional[Any] = None
    ):
        self.db = db or storage
        self.embedding_provider = embedding_provider

    def search_semantic(
        self,
        query_vector: List[float],
        top_k: int = 5,
        document_id: Optional[str] = None
    ) -> List[Tuple[Chunk, float]]:
        """
        Find top_k chunks matching query_vector by cosine similarity.
        Returns list of (Chunk, similarity_score) sorted descending by score.
        """
        if not query_vector:
            return []

        chunks = self.db.get_all_chunks_with_embeddings()
        if document_id:
            chunks = [c for c in chunks if c.document_id == document_id]

        if not chunks:
            return []

        q_arr = np.array(query_vector, dtype=np.float32)
        q_norm = np.linalg.norm(q_arr)
        if q_norm < 1e-9:
            return []

        q_unit = q_arr / q_norm

        chunk_vecs = [np.array(c.embedding, dtype=np.float32) for c in chunks if c.embedding]
        if not chunk_vecs:
            return []

        matrix = np.vstack(chunk_vecs)
        # Compute norms
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        # Avoid divide-by-zero
        norms = np.where(norms < 1e-9, 1.0, norms)
        matrix_unit = matrix / norms

        # Cosine similarities = dot product of unit vectors
        scores = np.dot(matrix_unit, q_unit)

        # Pair chunks with scores
        scored_pairs = []
        for i, score in enumerate(scores):
            # Clip between 0.0 and 1.0 (cosine sim ranges -1 to 1, map negatives to 0.0)
            clean_score = float(max(0.0, score))
            scored_pairs.append((chunks[i], clean_score))

        # Sort descending by score
        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        return scored_pairs[:top_k]
