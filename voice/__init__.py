"""
Voice processing package for TONY (Stage 2 & Stage 3).
Provides modular STT, TTS, VAD, and Wake-Word abstractions.
"""
from voice.stt_provider import STTProvider, STTProviderError, get_stt_provider
from voice.whisper_provider import WhisperSTTProvider
from voice.mock_stt_provider import MockSTTProvider
from voice.tts_provider import TTSProvider, TTSProviderError, get_tts_provider
from voice.local_tts_provider import LocalTTSProvider
from voice.mock_tts_provider import MockTTSProvider
from voice.vad import VADConfig, VoiceActivityDetector
from voice.wake_word import WakeWordDetector

__all__ = [
    "STTProvider",
    "STTProviderError",
    "get_stt_provider",
    "WhisperSTTProvider",
    "MockSTTProvider",
    "TTSProvider",
    "TTSProviderError",
    "get_tts_provider",
    "LocalTTSProvider",
    "MockTTSProvider",
    "VADConfig",
    "VoiceActivityDetector",
    "WakeWordDetector",
]
