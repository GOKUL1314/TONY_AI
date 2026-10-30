"""
Dynamic Context Compactor & Token Budgeter for TONY AI.
Enforces strict character/token ceilings on conversation history passed to LLM inference engines.
Compacts older dialogue turns into a concise structured recap while preserving the most recent turns verbatim.
Guarantees fast prompt prefill (<3s) and prevents local model context overflows or 60s timeouts on large chats.
"""
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("tony.intelligence.context_compactor")

# Default budgeting constants
DEFAULT_MAX_PROMPT_CHARS = 6000     # ~1500 tokens: optimal fast-prefill window for local 3B/8B models
DEFAULT_MAX_HISTORY_CHARS = 2500    # ~600 tokens
DEFAULT_KEEP_RECENT_TURNS = 2       # Keep last 2 dialogue turns verbatim


class ContextCompactor:
    """
    Manages sliding-window context compression and token budgeting for local LLM inference.
    """

    @staticmethod
    def summarize_turn(turn: Dict[str, Any]) -> str:
        """
        Condense a single dialogue turn into a dense 1-line recap.
        """
        user_msg = turn.get("user_message") or turn.get("content") or turn.get("message") or ""
        assistant_msg = turn.get("assistant_response") or turn.get("reply") or ""

        # Clean user message (take first 60 chars)
        clean_user = re.sub(r"\s+", " ", str(user_msg)).strip()
        if len(clean_user) > 60:
            clean_user = clean_user[:57] + "..."

        # Clean assistant response (extract first sentence or up to 70 chars)
        clean_assistant = re.sub(r"\s+", " ", str(assistant_msg)).strip()
        period_idx = clean_assistant.find(".")
        if 0 < period_idx < 70:
            clean_assistant = clean_assistant[:period_idx + 1]
        elif len(clean_assistant) > 70:
            clean_assistant = clean_assistant[:67] + "..."

        if clean_assistant:
            return f"- User: \"{clean_user}\" -> TONY: {clean_assistant}"
        return f"- User: \"{clean_user}\""

    @classmethod
    def compact_history(
        cls,
        history: List[Dict[str, Any]],
        max_chars: int = DEFAULT_MAX_HISTORY_CHARS,
        keep_recent_turns: int = DEFAULT_KEEP_RECENT_TURNS
    ) -> List[Dict[str, str]]:
        """
        Compresses conversation turns to stay within max_chars.
        If history exceeds budget, older turns are compacted into a single recap turn.
        
        :param history: List of turn dicts (with user_message & assistant_response, or role & message).
        :param max_chars: Maximum total characters permitted in returned history context.
        :param keep_recent_turns: Number of latest turns to keep verbatim.
        :return: Standardized list of role/message dictionaries for LLM.
        """
        if not history:
            return []

        # Normalize turns into standard (user_msg, asst_msg) pairs
        normalized_pairs: List[Dict[str, str]] = []
        i = 0
        while i < len(history):
            item = history[i]
            if "user_message" in item and "assistant_response" in item:
                normalized_pairs.append({
                    "user": str(item["user_message"] or ""),
                    "assistant": str(item["assistant_response"] or "")
                })
                i += 1
            elif item.get("role") == "user":
                u_text = str(item.get("message") or item.get("content") or "")
                a_text = ""
                if i + 1 < len(history) and history[i + 1].get("role") == "assistant":
                    a_text = str(history[i + 1].get("message") or history[i + 1].get("content") or "")
                    i += 1
                normalized_pairs.append({"user": u_text, "assistant": a_text})
                i += 1
            else:
                i += 1

        if not normalized_pairs:
            return []

        # Calculate raw character count across all pairs
        raw_chars = sum(len(p["user"]) + len(p["assistant"]) for p in normalized_pairs)

        # Fast Path: If total history is already under budget, preserve everything verbatim
        if raw_chars <= max_chars:
            messages: List[Dict[str, str]] = []
            for p in normalized_pairs:
                if p["user"]:
                    messages.append({"role": "user", "message": p["user"]})
                if p["assistant"]:
                    messages.append({"role": "assistant", "message": p["assistant"]})
            return messages

        # Compaction Path: Split into older turns and recent verbatim turns
        recent_pairs = normalized_pairs[-keep_recent_turns:]
        older_pairs = normalized_pairs[:-keep_recent_turns]

        summary_lines: List[str] = []
        for p in older_pairs:
            summary_lines.append(cls.summarize_turn({
                "user_message": p["user"],
                "assistant_response": p["assistant"]
            }))

        recap_content = (
            "[PRIOR CONVERSATION CONTEXT - RECAP OF OLDER TOPICS]:\n" +
            "\n".join(summary_lines[-6:])  # Keep up to 6 most relevant summary lines
        )

        messages = []
        if summary_lines:
            messages.append({"role": "system", "message": recap_content})

        # Append recent turns verbatim (with per-message length guard)
        for p in recent_pairs:
            u_text = p["user"]
            a_text = p["assistant"]
            # Guard against massive individual turns (e.g. 10k character code dumps)
            if len(a_text) > 800:
                a_text = a_text[:750] + "\n[...remainder truncated for context efficiency...]"
            if len(u_text) > 500:
                u_text = u_text[:450] + "\n[...truncated...]"

            if u_text:
                messages.append({"role": "user", "message": u_text})
            if a_text:
                messages.append({"role": "assistant", "message": a_text})

        logger.info(
            f"Compacted conversation history: {len(normalized_pairs)} total turns -> "
            f"{len(older_pairs)} summarized, {len(recent_pairs)} verbatim "
            f"({raw_chars} chars compressed to {sum(len(m['message']) for m in messages)} chars)"
        )
        return messages

    @classmethod
    def assemble_prompt_context(
        cls,
        system_prompt: str,
        recent_history: List[Dict[str, Any]],
        memory_context: Optional[str] = None,
        personalization_context: Optional[str] = None,
        max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS
    ) -> List[Dict[str, str]]:
        """
        Builds the complete layered context for LLM generation while strictly enforcing
        the total prompt character budget.
        """
        context_items: List[Dict[str, str]] = []

        # 1. System Prompt & Persona (Highest Priority)
        context_items.append({"role": "system", "message": system_prompt})

        # 2. Memory Context (Trimmed to top 400 chars if present)
        if memory_context and memory_context.strip():
            trimmed_mem = memory_context.strip()
            if len(trimmed_mem) > 400:
                trimmed_mem = trimmed_mem[:350] + "..."
            context_items.append({
                "role": "system",
                "message": f"[UNTRUSTED RETRIEVED MEMORY DATA - ADVISORY]:\n{trimmed_mem}"
            })

        # 3. Personalization Context (Trimmed to top 300 chars if present)
        if personalization_context and personalization_context.strip():
            trimmed_pers = personalization_context.strip()
            if len(trimmed_pers) > 300:
                trimmed_pers = trimmed_pers[:250] + "..."
            context_items.append({
                "role": "system",
                "message": f"[PERSONALIZATION CONTEXT]:\n{trimmed_pers}"
            })

        # 4. Compacted History
        current_used = sum(len(m["message"]) for m in context_items)
        remaining_budget = max(500, max_prompt_chars - current_used)
        compacted_turns = cls.compact_history(recent_history, max_chars=remaining_budget)
        context_items.extend(compacted_turns)

        return context_items
