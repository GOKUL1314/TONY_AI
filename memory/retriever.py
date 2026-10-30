"""
Memory retrieval and context building module for TONY (Stage 4).
Provides modular abstraction (MemoryRetriever) with keyword/category relevance scoring
and extensible support for future vector/semantic search.
"""
from abc import ABC, abstractmethod
import logging
import re
from typing import Any
from memory.manager import MemoryManager
from memory.models import MemoryItem

logger = logging.getLogger("tony.memory.retriever")

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "with", "by", "about", "like", "through",
    "over", "before", "after", "between", "under", "it", "its", "that", "this",
    "what", "which", "who", "whom", "how", "when", "where", "why", "can", "could",
    "will", "would", "do", "does", "did", "have", "has", "had", "i", "me", "my",
    "you", "your", "we", "our", "tell", "show", "give", "please", "tony"
}

# Domain keyword to memory_key mapping for intuitive recall
QUERY_INTENT_MAP = {
    "name": ["user_name", "identity"],
    "who am i": ["user_name", "identity"],
    "who is": ["user_name", "identity"],
    "language": ["user_language_preference", "preference"],
    "code": ["user_language_preference", "skill", "project"],
    "programming": ["user_language_preference", "skill"],
    "learning": ["user_learning_topic", "skill"],
    "learn": ["user_learning_topic", "skill"],
    "project": ["project_name", "project"],
    "working on": ["project_name", "user_learning_topic"],
    "favorite": ["favorite_"]
}


class MemoryRetriever(ABC):
    """
    Abstract Base Class for memory retrieval strategies.
    Allows seamlessly swapping between keyword relevance and vector semantic search.
    """

    def __init__(self, manager: MemoryManager, max_results: int = 5, min_relevance: float = 0.15):
        self.manager = manager
        self.max_results = max_results
        self.min_relevance = min_relevance

    @abstractmethod
    def retrieve_relevant(self, query: str, limit: int | None = None) -> list[MemoryItem]:
        """Retrieve memories relevant to the user query."""
        pass

    def retrieve(self, query: str, limit: int | None = None) -> list[MemoryItem]:
        """Convenience alias for retrieve_relevant."""
        return self.retrieve_relevant(query, limit=limit)

    def build_memory_context(self, query: str, limit: int | None = None) -> str:
        """
        Build a concise prompt context string containing relevant memories.

        :param query: Incoming user message.
        :param limit: Optional max items limit.
        :return: Formatted context string or empty string if no relevant memories found.
        """
        memories = self.retrieve_relevant(query, limit=limit)
        if not memories:
            return ""

        lines = ["RELEVANT USER MEMORY:"]
        for m in memories:
            # Human readable label
            label = m.memory_key.replace("user_", "").replace("_", " ").title()
            lines.append(f"- {label}: {m.memory_value}")

        context_str = "\n".join(lines)
        logger.debug(f"Injected memory context ({len(memories)} items) for query: '{query}'")
        return context_str


class KeywordMemoryRetriever(MemoryRetriever):
    """
    Fast, deterministic keyword and category relevance retriever.
    Scores memories by token overlap, domain intent match, importance tier, and recency.
    """

    def _extract_query_tokens(self, query: str) -> list[str]:
        """Extract meaningful alphanumeric tokens from query string."""
        raw_words = re.findall(r"\b[a-zA-Z0-9_\+\.#]+\b", query.lower())
        return [w for w in raw_words if w not in STOP_WORDS and len(w) > 1]

    def score_memory(self, memory: MemoryItem, query: str, tokens: list[str]) -> float:
        """
        Calculate a relevance score between 0.0 and 1.0 for a memory entity.
        """
        clean_query = query.lower()
        key_lower = memory.memory_key.lower()
        val_lower = memory.memory_value.lower()
        cat_lower = memory.category.lower()

        score = 0.0

        # 1. Domain Intent Match Boost
        for phrase, target_keys in QUERY_INTENT_MAP.items():
            if phrase in clean_query:
                for tk in target_keys:
                    if tk in key_lower or tk in cat_lower:
                        score += 0.55
                        break

        # 2. Token Matching across key, value, and category
        matched_tokens = 0
        for token in tokens:
            if token in key_lower:
                score += 0.35
                matched_tokens += 1
            elif token in val_lower:
                score += 0.40
                matched_tokens += 1
            elif token in cat_lower:
                score += 0.20
                matched_tokens += 1

        # 3. Exact Substring Boost
        if key_lower in clean_query:
            score += 0.4
        if len(val_lower) > 3 and val_lower in clean_query:
            score += 0.4

        # 4. Importance Multiplier
        # importance 5 adds 0.20, importance 1 adds 0.04
        score += (memory.importance / 5.0) * 0.20

        # 5. Access Frequency boost (logarithmic-like scale)
        if memory.access_count > 0:
            score += min(0.10, memory.access_count * 0.02)

        return min(1.0, score)

    def retrieve_relevant(self, query: str, limit: int | None = None) -> list[MemoryItem]:
        """
        Retrieve active memories scoring above relevance threshold.
        """
        max_items = limit or self.max_results
        tokens = self._extract_query_tokens(query)

        # Fetch all active memories to score in-memory (lightweight for desktop SQLite)
        all_active = self.manager.list_memories(is_active=True, limit=200)
        if not all_active:
            return []

        scored_memories: list[tuple[float, MemoryItem]] = []
        for mem in all_active:
            score = self.score_memory(mem, query, tokens)
            if score >= self.min_relevance:
                scored_memories.append((score, mem))

        # Sort descending by score
        scored_memories.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, mem in scored_memories[:max_items]:
            # Touch memory to update access timestamp
            self.manager.touch_memory(mem.id)
            results.append(mem)

        logger.info(f"Retrieved {len(results)} relevant memories for query '{query}' (scores: {[round(s, 2) for s, _ in scored_memories[:max_items]]})")
        return results


def get_memory_retriever(
    manager: MemoryManager,
    config
) -> MemoryRetriever:
    """
    Factory function for instantiating the memory retriever.
    Supports future expansion to semantic embeddings when MEMORY_SEMANTIC_SEARCH is enabled.
    """
    semantic_enabled = getattr(config, "MEMORY_SEMANTIC_SEARCH", False)
    max_results = getattr(config, "MEMORY_MAX_RESULTS", 5)
    min_relevance = getattr(config, "MEMORY_MIN_RELEVANCE", 0.15)

    if semantic_enabled:
        logger.info("Semantic memory search requested (stubbed for future extension). Falling back to KeywordMemoryRetriever.")

    return KeywordMemoryRetriever(
        manager=manager,
        max_results=max_results,
        min_relevance=min_relevance
    )
