"""
Local Text-to-Speech Provider using pyttsx3 (native Windows SAPI5).
Completely offline, zero-latency, and uses standard built-in operating system voices.
"""
import logging
from pathlib import Path
import threading
from typing import Any
from voice.tts_provider import TTSProvider, TTSProviderError

logger = logging.getLogger("tony.voice.tts.local")

# Lock to ensure thread-safe access to SAPI5 COM engine
_tts_lock = threading.Lock()


class LocalTTSProvider(TTSProvider):
    """
    Local TTS synthesizer leveraging Windows SAPI5 via pyttsx3.
    Operates without internet connection and produces clean WAV audio.
    """

    def __init__(self, voice: str = "default", rate: int = 175):
        super().__init__(voice=voice, rate=rate)
        self.provider_name = "Local (pyttsx3/SAPI5)"

    def synthesize(self, text: str, output_path: str | Path) -> Path:
        """
        Synthesize text into a WAV audio file on disk.

        :param text: Text to speak.
        :param output_path: Target output path.
        :return: Path to created WAV file.
        """
        clean_text = text.strip()
        if not clean_text:
            raise TTSProviderError("Cannot synthesize speech from empty text.")

        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        with _tts_lock:
            try:
                # Ensure Windows COM apartment is initialized for the calling thread
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except Exception:
                    pass

                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty("rate", self.rate)

                # Set voice if specified and not 'default'
                if self.voice != "default":
                    voices = engine.getProperty("voices")
                    for v in voices:
                        if self.voice.lower() in v.name.lower() or self.voice.lower() in v.id.lower():
                            engine.setProperty("voice", v.id)
                            break

                logger.info(f"Synthesizing {len(clean_text)} characters to {target.name}...")
                engine.save_to_file(clean_text, str(target))
                engine.runAndWait()

                if not target.exists() or target.stat().st_size == 0:
                    raise TTSProviderError("TTS engine failed to produce audio file.")

                logger.info(f"TTS synthesis complete: {target.name} ({target.stat().st_size} bytes)")
                return target

            except TTSProviderError:
                raise
            except Exception as e:
                err_msg = f"Failed to synthesize speech via pyttsx3: {str(e)}"
                logger.exception(err_msg)
                raise TTSProviderError(err_msg) from e

    def check_health(self) -> dict[str, Any]:
        """Verify pyttsx3 engine availability and list available voices."""
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass

            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            voice_names = [v.name for v in voices] if voices else []

            return {
                "available": True,
                "provider": self.provider_name,
                "voice": self.voice,
                "rate": self.rate,
                "available_voices": voice_names,
                "details": f"Local SAPI5 ready with {len(voice_names)} installed voice(s)."
            }
        except Exception as e:
            return {
                "available": False,
                "provider": self.provider_name,
                "details": f"Local TTS engine unavailable ({str(e)})."
            }
