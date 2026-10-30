"""
Keyword and Full-Text Search (FTS5) Engine for TONY AI (Stage 11).
Leverages SQLite FTS5 with BM25 ranking and token overlap for exact keyword,
symbol, and error-phrase matches.
"""
import logging
import re
from typing import List, Tuple, Optional, Dict, Any

from knowledge.models import Chunk
from knowledge.storage import KnowledgeDatabase

logger = logging.getLogger("tony.knowledge.keyword_search")


class KeywordSearchEngine:
    """Executes deterministic keyword and BM25 full-text queries over indexed chunks."""

    def __init__(self, db: Optional[KnowledgeDatabase] = None, storage: Optional[KnowledgeDatabase] = None):
        self.db = db or storage

    def search_keywords(
        self,
        query: str,
        top_k: int = 5,
        document_id: Optional[str] = None
    ) -> List[Tuple[Chunk, float]]:
        """
        Search chunks using FTS5 BM25 scoring with fallback to token overlap.
        Returns list of (Chunk, keyword_score) sorted descending by score (0.0 to 1.0).
        """
        if not query or not query.strip():
            return []

        clean_query = query.strip()
        tokens = re.findall(r"\b[a-zA-Z0-9_\-\.]+\b", clean_query)
        if not tokens:
            return []

        # 1. Try FTS5 MATCH
        fts_results = self._search_fts(tokens, top_k * 2, document_id)
        if fts_results:
            return fts_results[:top_k]

        # 2. Fallback to SQL LIKE / Token Overlap
        return self._search_fallback(tokens, top_k, document_id)

    def _search_fts(
        self,
        tokens: List[str],
        limit: int,
        document_id: Optional[str]
    ) -> List[Tuple[Chunk, float]]:
        """Query FTS5 virtual table using sanitized boolean OR tokens."""
        # Sanitize tokens for FTS5 (surround each with quotes)
        safe_terms = [f'"{t}"' for t in tokens if len(t) > 1]
        if not safe_terms:
            safe_terms = [f'"{t}"' for t in tokens]

        fts_query = " OR ".join(safe_terms)

        scored: List[Tuple[Chunk, float]] = []
        try:
            with self.db.get_cursor() as cur:
                if document_id:
                    sql = """
                        SELECT chunk_id, bm25(chunks_fts) as rank
                        FROM chunks_fts
                        WHERE chunks_fts MATCH ? AND document_id = ?
                        ORDER BY rank ASC
                        LIMIT ?;
                    """
                    cur.execute(sql, (fts_query, document_id, limit))
                else:
                    sql = """
                        SELECT chunk_id, bm25(chunks_fts) as rank
                        FROM chunks_fts
                        WHERE chunks_fts MATCH ?
                        ORDER BY rank ASC
                        LIMIT ?;
                    """
                    cur.execute(sql, (fts_query, limit))

                rows = cur.fetchall()
                if not rows:
                    return []

                # Convert BM25 negative score to positive normalized 0.0 - 1.0
                # Lower (more negative) is better in SQLite FTS5 bm25()
                for row in rows:
                    cid = row["chunk_id"]
                    rank = abs(row["rank"])
                    score = rank / (1.0 + rank)

                    # Retrieve chunk row
                    cur.execute("SELECT * FROM chunks WHERE id = ?", (cid,))
                    chk_row = cur.fetchone()
                    if chk_row:
                        chk = self.db._row_to_chunk(chk_row)
                        scored.append((chk, float(score)))

        except Exception as e:
            logger.debug(f"FTS5 search error: {e}")
            return []

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _search_fallback(
        self,
        tokens: List[str],
        limit: int,
        document_id: Optional[str]
    ) -> List[Tuple[Chunk, float]]:
        """Fallback token overlap scorer over all chunks."""
        with self.db.get_cursor() as cur:
            if document_id:
                cur.execute("SELECT * FROM chunks WHERE document_id = ?", (document_id,))
            else:
                cur.execute("SELECT * FROM chunks;")
            rows = cur.fetchall()

        if not rows:
            return []

        scored: List[Tuple[Chunk, float]] = []
        token_set = {t.lower() for t in tokens}

        for row in rows:
            chk = self.db._row_to_chunk(row)
            txt_lower = chk.text.lower()
            matched = sum(1 for t in token_set if t in txt_lower)
            if matched > 0:
                score = matched / len(token_set)
                scored.append((chk, float(score)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]
