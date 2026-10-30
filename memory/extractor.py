"""
Memory extraction and intent classification module for TONY (Stage 4).
Classifies user intent (REMEMBER, FORGET, RECALL, NORMAL), extracts key-value facts,
and enforces strict safety checks preventing the storage of credentials and secrets.
"""
from dataclasses import dataclass
from enum import Enum
import logging
import re
from typing import Any

logger = logging.getLogger("tony.memory.extractor")


class MemoryIntent(str, Enum):
    """Classified intention of user input regarding long-term memory."""
    REMEMBER = "REMEMBER"       # Explicit or implicit request to save info
    FORGET = "FORGET"           # Explicit request to remove info
    RECALL = "RECALL"           # Explicit inquiry about stored memories
    CLEAR = "CLEAR"             # Request to clear all memories
    NORMAL = "NORMAL"           # Normal conversation without memory directives


@dataclass
class ExtractedMemory:
    """Structured memory payload extracted from dialogue."""
    intent: MemoryIntent
    memory_key: str = ""
    memory_value: str = ""
    category: str = "other"
    importance: int = 2
    raw_text: str = ""
    target_pattern: str = ""    # For FORGET commands


# Sensitive secret detection patterns
SECRET_PATTERNS = [
    re.compile(r"(?i)\b(?:password|passwd|pwd)\s*(?:is|[:=])\s*\S+"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*(?:is|[:=])\s*\S+"),
    re.compile(r"(?i)\b(?:bearer(?:\s+token)?\s+[a-zA-Z0-9_\-\.]{8,})\b"),
    re.compile(r"\b(?:sk-[a-zA-Z0-9]{15,})\b"),           # OpenAI key format
    re.compile(r"\b(?:ghp_[a-zA-Z0-9]{15,})\b"),          # GitHub PAT
    re.compile(r"\b(?:\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4})\b"),  # Credit card
    re.compile(r"(?i)-----BEGIN (?:[A-Z0-9_-]+\s+)?(?:RSA|DSA|EC|OPENSSH|PRIVATE KEY)"),
]


def is_sensitive_secret(text: str) -> bool:
    """
    Check if a text string contains passwords, credentials, API keys, or financial data.
    """
    if not text:
        return False
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            logger.warning(f"Safety Trigger: Secret or credential pattern detected. Storing denied.")
            return True
    return False


class MemoryExtractor:
    """
    Analyzes user text to extract durable personal facts and parse memory commands.
    """

    def __init__(self):
        self._init_rules()

    def is_sensitive_secret(self, text: str) -> bool:
        """Check if text contains credentials, passwords, or secrets."""
        return is_sensitive_secret(text)

    def classify_intent(self, text: str) -> str:
        """Classify user text intent as REMEMBER, FORGET, RECALL, CLEAR, or NORMAL."""
        return self.extract(text).intent.value

    def extract_facts(self, text: str) -> list[dict[str, Any]]:
        """Extract structured facts as a list of dicts."""
        mem = self.extract(text)
        if mem and mem.memory_key and mem.memory_value:
            return [{
                "key": mem.memory_key,
                "value": mem.memory_value,
                "category": mem.category,
                "importance": mem.importance
            }]
        return []

    def _init_rules(self) -> None:
        """Compile regex patterns for intent classification and information extraction."""
        # 1. Explicit Remember commands
        # e.g. "Remember that my name is Gokul", "Remember that I prefer Python"
        self.remember_prefix_re = re.compile(
            r"^(?:tony[,!:]?\s*)?(?:please\s+)?(?:remember\s+(?:that\s+)?|don'?t\s+forget\s+(?:that\s+)?|keep\s+in\s+mind\s+(?:that\s+)?)",
            re.IGNORECASE
        )

        # 2. Explicit Forget commands
        # e.g. "Forget that I prefer Python", "Forget my name", "Clear my memories"
        self.forget_re = re.compile(
            r"^(?:tony[,!:]?\s*)?(?:please\s+)?(?:forget\s+(?:that\s+|about\s+|my\s+)?|delete\s+memory\s+(?:about\s+)?)",
            re.IGNORECASE
        )
        self.clear_all_re = re.compile(
            r"(?i)\b(?:clear\s+(?:all\s+)?(?:my\s+)?memories|delete\s+all\s+(?:my\s+)?memories|forget\s+everything)\b"
        )

        # 3. Explicit Recall commands
        # e.g. "What do you remember about me?", "Show me what you remember", "What is my name?"
        self.recall_all_re = re.compile(
            r"(?i)\b(?:what\s+do\s+you\s+remember\s+(?:about\s+me)?|show\s+(?:me\s+)?what\s+you\s+remember|list\s+(?:my\s+)?memories)\b"
        )

        # 4. Specific category extractors
        # Name / Identity
        self.name_re = re.compile(
            r"(?i)\b(?:my\s+name\s+is|i\s+am|call\s+me)\s+([A-Z][a-zA-Z\s]{1,25})\b"
        )
        # Programming Language Preference
        self.lang_pref_re = re.compile(
            r"(?i)\b(?:i\s+prefer|my\s+preferred\s+(?:programming\s+)?language\s+is|i\s+use|i\s+code\s+in)\s+([A-Za-z0-9#\+\.\s]+?)(?:[\.,;]|$|\s+over\s+|\s+for\s+)"
        )
        # Learning / Skills
        self.learning_re = re.compile(
            r"(?i)\b(?:i\s+am\s+learning|i'm\s+learning|currently\s+learning)\s+([A-Za-z0-9#\+\.\s]{2,30}?)(?:[\.,;]|$)"
        )
        # Project Name / Context
        self.project_re = re.compile(
            r"(?i)\b(?:my\s+project\s+is\s+(?:called\s+)?|i\s+am\s+(?:working\s+on|building|developing|creating)\s+(?:a\s+|an\s+)?(?:ai\s+|app\s+|bot\s+)?(?:called\s+)?|working\s+on\s+)\s*([A-Za-z0-9_\-\.\s]{2,35}?)(?:[\.,;]|$|\s+app|\s+system|\s+project)"
        )
        # Generic Preference (e.g. "my favorite X is Y", "I prefer X", "I prefer X in Y")
        self.generic_pref_re = re.compile(
            r"(?i)\b(?:my\s+favorite\s+([a-zA-Z\s]+?)\s+is\s+([a-zA-Z0-9\s]+?)|i\s+prefer\s+([a-zA-Z0-9\s]+?)(?:\s+(?:to|over|in|for)\s+[a-zA-Z0-9\s]+)?)(?:[\.,;]|$)"
        )

    def extract(self, text: str) -> ExtractedMemory:
        """
        Classify text and extract any durable personal memory items.
        """
        clean = text.strip()
        if not clean:
            return ExtractedMemory(intent=MemoryIntent.NORMAL, raw_text=text)

        # 1. Check for secret safety violation
        if is_sensitive_secret(clean):
            logger.warning("Message contained sensitive secret; skipping extraction.")
            return ExtractedMemory(intent=MemoryIntent.NORMAL, raw_text=clean)

        # 2. Check for Clear All Memory command
        if self.clear_all_re.search(clean):
            return ExtractedMemory(intent=MemoryIntent.CLEAR, raw_text=clean)

        # 3. Check for Recall All command
        if self.recall_all_re.search(clean):
            return ExtractedMemory(intent=MemoryIntent.RECALL, raw_text=clean)

        # 4. Check for Forget command
        if self.forget_re.search(clean):
            target = self.forget_re.sub("", clean).strip(" .,!?:;")
            return ExtractedMemory(
                intent=MemoryIntent.FORGET,
                target_pattern=target,
                raw_text=clean
            )

        # 5. Check for Explicit Remember command
        is_explicit_remember = bool(self.remember_prefix_re.search(clean))
        content_to_analyze = self.remember_prefix_re.sub("", clean).strip() if is_explicit_remember else clean

        # Parse specific entity patterns from content
        parsed = self._extract_specific_facts(content_to_analyze)
        if parsed:
            parsed.intent = MemoryIntent.REMEMBER
            parsed.source = "explicit" if is_explicit_remember else "extracted"
            parsed.raw_text = clean
            return parsed

        # If user explicitly commanded "Remember that <fact>", but no specialized regex matched:
        if is_explicit_remember and len(content_to_analyze) > 3:
            # Create a general instruction or fact memory
            key = self._generate_key_from_text(content_to_analyze)
            return ExtractedMemory(
                intent=MemoryIntent.REMEMBER,
                memory_key=key,
                memory_value=content_to_analyze.rstrip(" .!?;"),
                category="instruction" if "always" in content_to_analyze.lower() else "conversation",
                importance=3,
                raw_text=clean
            )

        # No memory directives or durable facts detected -> normal conversation
        return ExtractedMemory(intent=MemoryIntent.NORMAL, raw_text=clean)

    def _extract_specific_facts(self, text: str) -> ExtractedMemory | None:
        """Helper to match domain-specific patterns (name, language, learning, project)."""
        clean = text.strip()

        # Name / Identity (Importance 5)
        name_match = self.name_re.search(clean)
        if name_match:
            name_val = name_match.group(1).strip(" .,!?:;")
            first_w = name_val.split()[0].lower() if name_val else ""
            # Filter out non-names like "i am building", "i am happy", "i am learning"
            excluded = {
                "ready", "happy", "fine", "good", "busy", "learning", "trying",
                "going", "testing", "asking", "thinking", "here", "building",
                "creating", "working", "developing", "coding", "making", "an", "a", "the"
            }
            if first_w not in excluded and not first_w.endswith("ing") and len(name_val) >= 2:
                return ExtractedMemory(
                    intent=MemoryIntent.REMEMBER,
                    memory_key="user_name",
                    memory_value=name_val.title(),
                    category="identity",
                    importance=5
                )

        # Project Name (Importance 4)
        proj_match = self.project_re.search(clean)
        if proj_match:
            proj_val = proj_match.group(1).strip(" .,!?:;")
            if len(proj_val) >= 2 and proj_val.lower() not in {"it", "something", "stuff"}:
                return ExtractedMemory(
                    intent=MemoryIntent.REMEMBER,
                    memory_key="project_name",
                    memory_value=proj_val,
                    category="project",
                    importance=4
                )

        # Learning / Skill (Importance 3)
        learn_match = self.learning_re.search(clean)
        if learn_match:
            topic_val = learn_match.group(1).strip(" .,!?:;")
            if len(topic_val) >= 2:
                return ExtractedMemory(
                    intent=MemoryIntent.REMEMBER,
                    memory_key="user_learning_topic",
                    memory_value=topic_val,
                    category="skill",
                    importance=3
                )

        # Language Preference (Importance 3)
        lang_match = self.lang_pref_re.search(clean)
        if lang_match:
            lang_val = lang_match.group(1).strip(" .,!?:;")
            if len(lang_val) >= 2:
                return ExtractedMemory(
                    intent=MemoryIntent.REMEMBER,
                    memory_key="user_language_preference",
                    memory_value=lang_val,
                    category="preference",
                    importance=3
                )

        # Favorite X is Y or I prefer X
        fav_match = self.generic_pref_re.search(clean)
        if fav_match:
            if fav_match.group(1) and fav_match.group(2):
                subject = fav_match.group(1).strip().replace(" ", "_").lower()
                val = fav_match.group(2).strip()
                return ExtractedMemory(
                    intent=MemoryIntent.REMEMBER,
                    memory_key=f"favorite_{subject}",
                    memory_value=val,
                    category="preference",
                    importance=2
                )
            elif fav_match.group(3):
                val = fav_match.group(3).strip()
                return ExtractedMemory(
                    intent=MemoryIntent.REMEMBER,
                    memory_key="user_preference",
                    memory_value=val,
                    category="preference",
                    importance=3
                )

        return None

    def _generate_key_from_text(self, text: str) -> str:
        """Derive a clean normalized snake_case key from a descriptive fact."""
        # Strip common stop words
        words = [w for w in re.findall(r"\b[a-zA-Z0-9]+\b", text.lower()) if w not in {"that", "the", "a", "an", "i", "my", "to", "and", "is", "am", "are"}]
        key = "_".join(words[:4])
        return key or "user_note"
