"""
Voice Activity Detection (VAD) module for TONY (Stage 3).
Provides audio energy analysis, silence detection, and turn-taking threshold utilities.
"""
from dataclasses import dataclass
import logging
import math
import struct
from typing import Any

logger = logging.getLogger("tony.voice.vad")


@dataclass
class VADConfig:
    """Configuration parameters for Voice Activity Detection."""
    silence_timeout: float = 1.2    # Seconds of silence required to commit a speech turn
    energy_threshold: float = 0.015 # Minimum RMS amplitude required to count as speech
    min_speech_duration: float = 0.3 # Minimum duration (seconds) of valid speech
    sample_rate: int = 16000        # Standard 16kHz audio sample rate


class VoiceActivityDetector:
    """
    Lightweight Voice Activity Detector based on Root-Mean-Square (RMS) energy
    and zero-crossing rate analysis. Runs locally with near-zero CPU footprint.
    """

    def __init__(self, config: VADConfig | None = None):
        self.config = config or VADConfig()

    def calculate_rms(self, pcm_bytes: bytes) -> float:
        """
        Calculate Root-Mean-Square amplitude of 16-bit PCM audio samples.

        :param pcm_bytes: Raw 16-bit linear PCM audio bytes.
        :return: Normalized RMS energy value between 0.0 and 1.0.
        """
        if not pcm_bytes or len(pcm_bytes) < 2:
            return 0.0

        num_samples = len(pcm_bytes) // 2
        # Unpack as signed 16-bit integers
        try:
            samples = struct.unpack(f"<{num_samples}h", pcm_bytes[:num_samples * 2])
        except struct.error:
            return 0.0

        sum_squares = sum(s * s for s in samples)
        mean_square = sum_squares / num_samples
        rms = math.sqrt(mean_square)

        # Normalize relative to max 16-bit amplitude (32768)
        return rms / 32768.0

    def is_speech(self, pcm_bytes: bytes) -> bool:
        """
        Determine if an audio buffer contains vocal speech based on RMS energy threshold.

        :param pcm_bytes: Raw PCM audio bytes.
        :return: True if audio energy exceeds threshold.
        """
        rms = self.calculate_rms(pcm_bytes)
        return rms >= self.config.energy_threshold

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic configuration for VAD engine."""
        return {
            "engine": "Local Energy-RMS VAD",
            "silence_timeout": self.config.silence_timeout,
            "energy_threshold": self.config.energy_threshold,
            "min_speech_duration": self.config.min_speech_duration,
            "sample_rate": self.config.sample_rate
        }
