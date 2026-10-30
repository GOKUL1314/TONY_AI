"""
Conversation summarization module for TONY (Stage 4).
Distills long conversation dialogues into compact episodic summaries to preserve context
without exceeding LLM context windows.
"""
from datetime import datetime
import logging
from typing import Any
from memory.manager import MemoryManager

logger = logging.getLogger("tony.memory.summary")


class ConversationSummarizer:
    """
    Lightweight summarizer condensing conversation history turns into episodic memory.
    """

    def __init__(self, memory_manager: MemoryManager | None = None, threshold_turns: int = 15):
        self.memory_manager = memory_manager
        self.threshold_turns = threshold_turns

    def should_summarize(self, turns_count: int) -> bool:
        """Check if dialogue history length has crossed summarization threshold."""
        return turns_count >= self.threshold_turns

    def summarize_turns(self, turns: list[dict[str, Any]]) -> str:
        """
        Generate a concise textual synopsis of past dialogue exchanges.

        :param turns: List of dialogue turn dictionaries [{'user_message': '...', 'assistant_response': '...'}]
        :return: Concise summary string.
        """
        if not turns:
            return ""

        user_topics = []
        for t in turns:
            msg = t.get("user_message", "").strip()
            if msg and len(msg) > 3:
                # Capture main subject phrases
                snippet = msg[:60] + ("..." if len(msg) > 60 else "")
                user_topics.append(snippet)

        topics_sample = user_topics[:6]
        summary_text = f"Discussion topics ({len(turns)} turns): " + "; ".join(topics_sample)

        # Optionally persist summary as episodic memory
        if self.memory_manager:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M")
            self.memory_manager.save_memory(
                memory_key=f"summary_{timestamp_str}",
                memory_value=summary_text,
                category="conversation",
                importance=2,
                source="summary"
            )
            logger.info(f"Persisted episodic dialogue summary to long-term memory: '{summary_text}'")

        return summary_text
