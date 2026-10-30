"""
Whisper STT Provider using faster-whisper.
Optimized for local CPU/GPU speech-to-text inference with low memory footprint.
"""
import logging
from pathlib import Path
from typing import Any
from voice.stt_provider import STTProvider, STTProviderError

logger = logging.getLogger("tony.voice.whisper")


class WhisperSTTProvider(STTProvider):
    """
    Lightweight Whisper transcription engine using CTranslate2 backend.
    Loads models lazily on first transcription to ensure rapid server startup.
    """

    def __init__(
        self,
        model_name: str = "tiny",
        device: str = "cpu",
        compute_type: str = "int8"
    ):
        super().__init__(model_name=model_name)
        self.device = device
        self.compute_type = compute_type
        self.provider_name = "Whisper (local)"
        self._model = None

    def _get_model(self):
        """Lazy-load the Whisper model on first invocation."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                logger.info(
                    f"Loading Whisper model '{self.model_name}' on {self.device} ({self.compute_type})..."
                )
                self._model = WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type
                )
                logger.info(f"Whisper model '{self.model_name}' loaded successfully.")
            except ImportError as e:
                err_msg = (
                    "The 'faster-whisper' package is not installed. "
                    "Run: pip install faster-whisper, or set STT_PROVIDER=mock in .env."
                )
                logger.error(err_msg)
                raise STTProviderError(err_msg) from e
            except Exception as e:
                err_msg = f"Failed to initialize Whisper model '{self.model_name}': {str(e)}"
                logger.exception(err_msg)
                raise STTProviderError(err_msg) from e
        return self._model

    def transcribe(self, audio_path: str | Path) -> str:
        """
        Transcribe audio recording from file.

        :param audio_path: Path to audio file.
        :return: Transcribed text string.
        """
        path = Path(audio_path)
        if not path.exists():
            raise STTProviderError(f"Audio file not found: {path}")

        file_size = path.stat().st_size
        if file_size == 0:
            raise STTProviderError("Audio file is empty (0 bytes). Please record audio before transcribing.")

        try:
            model = self._get_model()
            logger.info(f"Transcribing audio file ({file_size} bytes): {path.name}")
            
            segments, info = model.transcribe(
                str(path),
                beam_size=5,
                language="en",
                vad_filter=True  # Voice activity detection to trim silence
            )

            text_segments = [s.text.strip() for s in segments if s.text.strip()]
            transcription = " ".join(text_segments).strip()

            logger.info(f"Transcription complete (detected lang: {info.language}): '{transcription}'")
            return transcription

        except STTProviderError:
            raise
        except Exception as e:
            err_msg = f"Whisper transcription failed: {str(e)}"
            logger.error(err_msg)
            raise STTProviderError(err_msg) from e

    def check_health(self) -> dict[str, Any]:
        """Diagnostic check for Whisper STT engine."""
        try:
            import faster_whisper
            return {
                "available": True,
                "provider": self.provider_name,
                "model": self.model_name,
                "device": self.device,
                "compute_type": self.compute_type,
                "model_cached": self._model is not None,
                "details": f"faster-whisper v{faster_whisper.__version__} ready."
            }
        except Exception as e:
            return {
                "available": False,
                "provider": self.provider_name,
                "model": self.model_name,
                "details": f"Whisper engine unavailable ({str(e)})."
            }
