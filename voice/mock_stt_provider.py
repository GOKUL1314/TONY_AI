"""
Mock STT Provider for testing and offline environments.
Returns predictable transcription without requiring neural network execution.
"""
import logging
from pathlib import Path
from typing import Any
from voice.stt_provider import STTProvider, STTProviderError

logger = logging.getLogger("tony.voice.stt.mock")


class MockSTTProvider(STTProvider):
    """
    Mock speech-to-text provider for automated tests and offline evaluation.
    """

    def __init__(self, model_name: str = "mock-stt"):
        super().__init__(model_name=model_name)
        self.provider_name = "mock_stt"

    def transcribe(self, audio_path: str | Path) -> str:
        """Simulate transcription from an audio file."""
        path = Path(audio_path)
        if not path.exists():
            raise STTProviderError(f"Audio file not found: {path}")

        if path.stat().st_size == 0:
            raise STTProviderError("Audio file is empty.")

        logger.info(f"Mock STT transcribed mock file: {path.name}")
        return "Hello Tony"

    def check_health(self) -> dict[str, Any]:
        """Mock STT is always available."""
        return {
            "available": True,
            "provider": self.provider_name,
            "model": self.model_name,
            "details": "Mock STT active. Suitable for automated testing."
        }
