"""
Text-to-Speech (TTS) Provider abstraction layer for TONY.
Enables swapping between native local voices, neural TTS engines, or cloud synthesis.
"""
from abc import ABC, abstractmethod
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("tony.voice.tts")


class TTSProviderError(Exception):
    """Exception raised for errors during speech synthesis."""
    pass


class TTSProvider(ABC):
    """
    Abstract Base Class for Text-to-Speech synthesis engines.
    """

    def __init__(self, voice: str = "default", rate: int = 175):
        self.voice = voice
        self.rate = rate
        self.provider_name = "generic_tts"

    @abstractmethod
    def synthesize(self, text: str, output_path: str | Path) -> Path:
        """
        Synthesize text into an audio file (e.g. WAV).

        :param text: Text string to speak.
        :param output_path: Target audio file path.
        :return: Path to generated audio file.
        """
        pass

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        """
        Check health and capabilities of the TTS engine.

        :return: Dict containing availability status and engine details.
        """
        pass


def get_tts_provider(config) -> TTSProvider:
    """
    Factory function to instantiate the configured TTS provider.

    :param config: The application Config object.
    :return: An instance of TTSProvider.
    """
    provider_type = config.TTS_PROVIDER.lower().strip()
    logger.info(f"Initializing TTS Provider: '{provider_type}' [Voice: '{config.TTS_VOICE}']")

    if provider_type == "local":
        from voice.local_tts_provider import LocalTTSProvider
        return LocalTTSProvider(
            voice=config.TTS_VOICE,
            rate=config.TTS_RATE,
        )
    elif provider_type == "mock":
        from voice.mock_tts_provider import MockTTSProvider
        return MockTTSProvider(voice=config.TTS_VOICE)
    else:
        raise ValueError(
            f"Unsupported TTS_PROVIDER '{provider_type}'. Supported: 'local', 'mock'."
        )
