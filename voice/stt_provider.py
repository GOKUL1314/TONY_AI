"""
Speech-to-Text (STT) Provider abstraction layer for TONY.
Enables swapping between different transcription engines (Whisper, mock, cloud, etc.).
"""
from abc import ABC, abstractmethod
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("tony.voice.stt")


class STTProviderError(Exception):
    """Exception raised for errors during speech transcription."""
    pass


class STTProvider(ABC):
    """
    Abstract Base Class for Speech-to-Text inference engines.
    """

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.provider_name = "generic_stt"

    @abstractmethod
    def transcribe(self, audio_path: str | Path) -> str:
        """
        Transcribe audio file into text.

        :param audio_path: Path to the recorded audio file.
        :return: Transcribed text string.
        """
        pass

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        """
        Check health and status of the STT engine.

        :return: Dict containing availability status and engine details.
        """
        pass


def get_stt_provider(config) -> STTProvider:
    """
    Factory function to instantiate the configured STT provider.

    :param config: The application Config object.
    :return: An instance of STTProvider.
    """
    provider_type = config.STT_PROVIDER.lower().strip()
    logger.info(f"Initializing STT Provider: '{provider_type}' [Model: '{config.STT_MODEL}']")

    if provider_type == "whisper":
        from voice.whisper_provider import WhisperSTTProvider
        return WhisperSTTProvider(
            model_name=config.STT_MODEL,
            device=config.STT_DEVICE,
            compute_type=config.STT_COMPUTE_TYPE,
        )
    elif provider_type == "mock":
        from voice.mock_stt_provider import MockSTTProvider
        return MockSTTProvider(model_name=config.STT_MODEL)
    else:
        raise ValueError(
            f"Unsupported STT_PROVIDER '{provider_type}'. Supported: 'whisper', 'mock'."
        )
