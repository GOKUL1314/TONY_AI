"""
Wake-word detection module for TONY AI.
Provides local phrase detection ("Tony", "Hey Tony", "Okay Tony") and prompt extraction
with confidence thresholding, debounce cooldown, and active conversation retention.
"""
import logging
import re
import time
from typing import Any, Tuple, Optional

logger = logging.getLogger("tony.voice.wakeword")


class WakeWordDetector:
    """
    Local Wake-Word Detector with 'Tony' as the primary wake phrase.
    Features confidence thresholding, debounce cooldown, and active dialogue retention.
    """

    def __init__(
        self,
        primary_phrase: str = "tony",
        allow_single_name: bool = True,
        confidence_threshold: float = 0.65,
        cooldown_ms: int = 1500
    ):
        self.primary_phrase = primary_phrase.lower().strip()
        self.allow_single_name = allow_single_name
        self.confidence_threshold = confidence_threshold
        self.cooldown_ms = cooldown_ms
        self.last_activation_time = 0.0
        self._last_detected_text = ""
        self._compile_patterns()

    def reset_cooldown(self) -> None:
        """Reset cooldown debounce timer."""
        self.last_activation_time = 0.0
        self._last_detected_text = ""

    def _compile_patterns(self) -> None:
        """Compile regex patterns for wake phrases, ordering longer multi-word triggers first."""
        # Multi-word triggers first to prevent greedy premature single-token capture
        patterns = [
            r"\bhey\s+tony\b",
            r"\bhi\s+tony\b",
            r"\bokay\s+tony\b",
            r"\bok\s+tony\b"
        ]
        if self.allow_single_name:
            patterns.append(r"\btony\b")

        self.combined_regex = re.compile(f"^.*?(?:{'|'.join(patterns)})[,!?:;.]*\\s*", re.IGNORECASE)
        self.trigger_regex = re.compile(f"(?:{'|'.join(patterns)})", re.IGNORECASE)

    def detect(
        self,
        text: str,
        confidence: float = 1.0,
        is_active_conversation: bool = False
    ) -> Tuple[bool, str, str]:
        """
        Check if text begins with or contains a wake phrase.

        :param text: Transcribed speech text.
        :param confidence: STT / audio confidence score (0.0 to 1.0).
        :param is_active_conversation: If True, allows subsequent turns without requiring wake word.
        :return: Tuple of (detected: bool, matched_phrase: str, trailing_prompt: str)
        """
        if not text or not text.strip():
            return False, "", ""

        clean = text.strip()

        # 1. False Activation Guard: STT Confidence Threshold
        if confidence < self.confidence_threshold:
            logger.debug(f"Wake detection rejected: Confidence {confidence} below threshold {self.confidence_threshold}")
            return False, "", clean

        match = self.combined_regex.match(clean)

        if match:
            # 2. Debounce / Cooldown Check for repeated trigger from same utterance
            now = time.time()
            elapsed_ms = (now - self.last_activation_time) * 1000.0
            if self.last_activation_time > 0 and elapsed_ms < self.cooldown_ms:
                if clean.lower() == self._last_detected_text.lower():
                    logger.debug(f"Wake detection debounced: {elapsed_ms:.1f}ms since last activation (< {self.cooldown_ms}ms)")
                    return False, "", clean

            matched_raw = match.group(0)
            trigger_match = self.trigger_regex.search(matched_raw)
            phrase = trigger_match.group(0).lower() if trigger_match else self.primary_phrase
            remaining_prompt = clean[match.end():].strip()

            self.last_activation_time = now
            self._last_detected_text = clean
            logger.info(f"Wake word detected: '{phrase}'. Remaining prompt: '{remaining_prompt}'")
            return True, phrase, remaining_prompt

        # 3. Active Conversation Turn Retention
        # When user is already in an active conversational turn, wake word is not required for subsequent turns
        if is_active_conversation and clean:
            logger.info(f"Active conversation turn accepted without wake word prefix: '{clean}'")
            return True, "active_conversation", clean

        return False, "", clean

    def is_wake_word_only(self, text: str) -> bool:
        """Return True if text contains only the wake phrase with no trailing command."""
        if not text or not text.strip():
            return False
        clean = text.strip()
        match = self.combined_regex.match(clean)
        if match:
            remaining = clean[match.end():].strip()
            return len(remaining) == 0
        return False

    def get_wake_response(self) -> str:
        """Official JARVIS-style wake response acknowledgment."""
        return "Yes, Sir."

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic status for wake word system."""
        return {
            "engine": "Local Pattern Wake Detector",
            "primary_phrase": self.primary_phrase,
            "allow_single_name": self.allow_single_name,
            "confidence_threshold": self.confidence_threshold,
            "cooldown_ms": self.cooldown_ms,
            "wake_response": "Yes, Sir.",
            "supported_triggers": ["Tony", "Okay Tony", "Hey Tony", "Hi Tony"] if self.allow_single_name else ["Hey Tony", "Okay Tony"]
        }
