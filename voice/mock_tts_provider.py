"""
Mock TTS Provider for testing and offline environments.
Generates lightweight valid WAV audio headers without requiring audio drivers.
"""
import logging
from pathlib import Path
import struct
from typing import Any
from voice.tts_provider import TTSProvider, TTSProviderError

logger = logging.getLogger("tony.voice.tts.mock")


class MockTTSProvider(TTSProvider):
    """
    Mock TTS synthesizer generating minimal valid WAV audio files.
    """

    def __init__(self, voice: str = "mock-voice", rate: int = 175):
        super().__init__(voice=voice, rate=rate)
        self.provider_name = "mock_tts"

    def synthesize(self, text: str, output_path: str | Path) -> Path:
        """Create a valid empty WAV audio file for testing."""
        clean_text = text.strip()
        if not clean_text:
            raise TTSProviderError("Cannot synthesize empty text.")

        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Generate minimal valid 44-byte WAV header (1 second silence at 8000Hz 8-bit mono)
        sample_rate = 8000
        num_samples = 800
        data_size = num_samples
        file_size = 36 + data_size

        wav_header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            file_size,
            b'WAVE',
            b'fmt ',
            16,
            1,  # PCM
            1,  # Mono
            sample_rate,
            sample_rate,  # Byte rate
            1,  # Block align
            8,  # Bits per sample
            b'data',
            data_size
        )
        silence = b'\x80' * num_samples

        with open(target, 'wb') as f:
            f.write(wav_header + silence)

        logger.info(f"Mock TTS generated mock audio file: {target.name}")
        return target

    def check_health(self) -> dict[str, Any]:
        """Mock TTS is always available."""
        return {
            "available": True,
            "provider": self.provider_name,
            "voice": self.voice,
            "details": "Mock TTS engine operational."
        }
