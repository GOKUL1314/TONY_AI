"""
Voice API routes for TONY (Stage 2 & Stage 3).
Provides endpoints for audio transcription (STT), speech synthesis (TTS),
wake-word verification, VAD telemetry, and continuous conversation settings.
"""
import logging
from pathlib import Path
import uuid
from flask import Blueprint, current_app, jsonify, request, send_file
from voice.stt_provider import STTProviderError
from voice.tts_provider import TTSProviderError
from voice.wake_word import WakeWordDetector
from voice.vad import VoiceActivityDetector, VADConfig

logger = logging.getLogger("tony.routes.voice")

voice_bp = Blueprint("voice", __name__, url_prefix="/api/voice")

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB max


def _get_voice_services():
    """Retrieve STT and TTS providers from application context."""
    stt_provider = current_app.config.get("STT_PROVIDER_INSTANCE")
    tts_provider = current_app.config.get("TTS_PROVIDER_INSTANCE")
    audio_dir = current_app.config.get("AUDIO_DIR", Path("data/audio"))
    wake_detector = current_app.config.get("WAKE_DETECTOR_INSTANCE")
    vad_detector = current_app.config.get("VAD_DETECTOR_INSTANCE")

    if wake_detector is None:
        wake_detector = WakeWordDetector(
            primary_phrase=current_app.config.get("WAKE_WORD", "hey tony"),
            allow_single_name=True
        )
        current_app.config["WAKE_DETECTOR_INSTANCE"] = wake_detector

    if vad_detector is None:
        silence_timeout = float(current_app.config.get("VOICE_SILENCE_TIMEOUT", 1.2))
        vad_detector = VoiceActivityDetector(VADConfig(silence_timeout=silence_timeout))
        current_app.config["VAD_DETECTOR_INSTANCE"] = vad_detector

    return stt_provider, tts_provider, Path(audio_dir), wake_detector, vad_detector


@voice_bp.route("/transcribe", methods=["POST"])
def transcribe():
    """
    Transcribe recorded microphone audio to text.
    Accepts multipart/form-data ('audio' file) or raw binary audio.
    Returns JSON: {"text": "...", "provider": "...", "model": "..."}
    """
    stt_provider, _, audio_dir, _, _ = _get_voice_services()
    if not stt_provider:
        return jsonify({"error": "STT transcription service is uninitialized."}), 500

    audio_dir.mkdir(parents=True, exist_ok=True)
    temp_input = audio_dir / f"input_{uuid.uuid4().hex[:8]}.wav"

    try:
        # 1. Extract audio bytes from multipart form or binary payload
        if "audio" in request.files:
            file_obj = request.files["audio"]
            if not file_obj.filename:
                return jsonify({"error": "Audio file part was provided but filename is empty."}), 400
            file_obj.save(temp_input)
        elif request.data:
            if len(request.data) > MAX_AUDIO_BYTES:
                return jsonify({"error": "Audio payload exceeds maximum size limit (25 MB)."}), 413
            with open(temp_input, "wb") as f:
                f.write(request.data)
        else:
            return jsonify({"error": "No audio payload detected in request. Expected multipart 'audio' or raw audio bytes."}), 400

        # 2. Check for empty audio file
        if not temp_input.exists() or temp_input.stat().st_size == 0:
            return jsonify({"error": "Received empty audio recording (0 bytes)."}), 400

        if temp_input.stat().st_size > MAX_AUDIO_BYTES:
            return jsonify({"error": "Audio payload exceeds maximum size limit (25 MB)."}), 413

        # 3. Transcribe via STT provider
        logger.info(f"Processing transcription request with {stt_provider.provider_name}...")
        transcription_text = stt_provider.transcribe(temp_input)

        return jsonify({
            "text": transcription_text,
            "provider": getattr(stt_provider, "provider_name", "unknown"),
            "model": getattr(stt_provider, "model_name", "unknown")
        }), 200

    except STTProviderError as e:
        logger.error(f"STT Error during transcription: {str(e)}")
        return jsonify({
            "error": str(e),
            "provider": getattr(stt_provider, "provider_name", "unknown")
        }), 503

    except Exception as e:
        logger.exception(f"Unexpected error in voice transcription: {str(e)}")
        return jsonify({
            "error": "Failed to process audio transcription.",
            "details": str(e)
        }), 500

    finally:
        # Clean up temporary uploaded audio
        if temp_input.exists():
            try:
                temp_input.unlink()
            except Exception as e:
                logger.warning(f"Could not delete temporary audio file {temp_input}: {e}")


@voice_bp.route("/speak", methods=["POST"])
def speak():
    """
    Synthesize text to speech audio.
    Expects JSON: {"text": "..."}
    Returns binary audio stream (audio/wav).
    """
    _, tts_provider, audio_dir, _, _ = _get_voice_services()
    if not tts_provider:
        return jsonify({"error": "TTS synthesis service is uninitialized."}), 500

    if not request.is_json:
        return jsonify({"error": "Invalid request. Content-Type must be application/json."}), 400

    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "The 'text' field is required in JSON payload."}), 400

    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "The 'text' field must be a non-empty string."}), 400

    clean_text = text.strip()
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_filename = f"tts_{uuid.uuid4().hex[:8]}.wav"
    output_path = audio_dir / output_filename

    try:
        logger.info(f"Synthesizing voice response ({len(clean_text)} chars)...")
        generated_file = tts_provider.synthesize(clean_text, output_path)

        if not generated_file.exists():
            raise TTSProviderError("Output audio file was not created by the TTS engine.")

        # Send generated WAV audio file
        return send_file(
            generated_file,
            mimetype="audio/wav",
            as_attachment=False,
            download_name="tony_voice.wav"
        )

    except TTSProviderError as e:
        logger.error(f"TTS Error during speech synthesis: {str(e)}")
        return jsonify({
            "error": str(e),
            "provider": getattr(tts_provider, "provider_name", "unknown")
        }), 503

    except Exception as e:
        logger.exception(f"Unexpected error during speech synthesis: {str(e)}")
        return jsonify({
            "error": "Failed to synthesize speech audio.",
            "details": str(e)
        }), 500


@voice_bp.route("/wake-check", methods=["POST"])
def wake_check():
    """
    Check if speech or text contains the local wake phrase ('Tony', 'Hey Tony', 'Okay Tony').
    Expects JSON: {"text": "...", "confidence": float (optional), "is_active_conversation": bool (optional)}
    Returns JSON: {"detected": bool, "wake_phrase": "...", "trailing_prompt": "...", "wake_only": bool, "wake_response": "Yes, Sir."}
    """
    _, _, _, wake_detector, _ = _get_voice_services()

    if not request.is_json:
        return jsonify({"error": "Invalid request. Content-Type must be application/json."}), 400

    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "The 'text' field is required."}), 400

    text = data.get("text", "")
    if not isinstance(text, str):
        return jsonify({"error": "The 'text' field must be a string."}), 400

    confidence = float(data.get("confidence", 1.0))
    is_active = bool(data.get("is_active_conversation", False))

    detected, phrase, trailing = wake_detector.detect(text, confidence=confidence, is_active_conversation=is_active)
    is_only = wake_detector.is_wake_word_only(text)

    return jsonify({
        "detected": detected,
        "wake_phrase": phrase,
        "trailing_prompt": trailing,
        "wake_only": is_only,
        "wake_response": "Yes, Sir."
    }), 200


@voice_bp.route("/config", methods=["GET", "POST"])
def voice_config():
    """Get or update continuous conversation & voice settings."""
    if request.method == "POST":
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json."}), 400
        data = request.get_json(silent=True) or {}

        if "continuous_mode" in data:
            current_app.config["CONTINUOUS_MODE"] = bool(data["continuous_mode"])
        if "wake_word_enabled" in data:
            current_app.config["WAKE_WORD_ENABLED"] = bool(data["wake_word_enabled"])
        if "wake_word" in data and isinstance(data["wake_word"], str) and data["wake_word"].strip():
            current_app.config["WAKE_WORD"] = data["wake_word"].strip().lower()
        if "wake_word_confidence" in data:
            try:
                current_app.config["WAKE_WORD_CONFIDENCE"] = float(data["wake_word_confidence"])
            except (ValueError, TypeError):
                pass
        if "wake_word_cooldown_ms" in data:
            try:
                current_app.config["WAKE_WORD_COOLDOWN_MS"] = int(data["wake_word_cooldown_ms"])
            except (ValueError, TypeError):
                pass
        if "voice_silence_timeout" in data:
            try:
                timeout_val = float(data["voice_silence_timeout"])
                if timeout_val > 0.3:
                    current_app.config["VOICE_SILENCE_TIMEOUT"] = timeout_val
                    # Update active VAD
                    vad = current_app.config.get("VAD_DETECTOR_INSTANCE")
                    if vad:
                        vad.config.silence_timeout = timeout_val
            except (ValueError, TypeError):
                pass
        if "microphone_enabled" in data:
            current_app.config["MICROPHONE_ENABLED"] = bool(data["microphone_enabled"])
        if "audio_ducking" in data:
            current_app.config["AUDIO_DUCKING"] = bool(data["audio_ducking"])

    # Return current state
    return jsonify({
        "continuous_mode": current_app.config.get("CONTINUOUS_MODE", True),
        "wake_word_enabled": current_app.config.get("WAKE_WORD_ENABLED", True),
        "wake_word": current_app.config.get("WAKE_WORD", "tony"),
        "wake_word_confidence": current_app.config.get("WAKE_WORD_CONFIDENCE", 0.65),
        "wake_word_cooldown_ms": current_app.config.get("WAKE_WORD_COOLDOWN_MS", 1500),
        "voice_silence_timeout": current_app.config.get("VOICE_SILENCE_TIMEOUT", 1.2),
        "microphone_enabled": current_app.config.get("MICROPHONE_ENABLED", True),
        "audio_ducking": current_app.config.get("AUDIO_DUCKING", True)
    }), 200


@voice_bp.route("/status", methods=["GET"])
def voice_status():
    """Diagnostic health check for STT, TTS, VAD, and Wake-Word engines."""
    stt_provider, tts_provider, _, wake_detector, vad_detector = _get_voice_services()
    return jsonify({
        "status": "online",
        "stt": stt_provider.check_health() if stt_provider else {"available": False},
        "tts": tts_provider.check_health() if tts_provider else {"available": False},
        "vad": vad_detector.get_diagnostics() if vad_detector else {"available": False},
        "wake_word": wake_detector.get_diagnostics() if wake_detector else {"available": False}
    }), 200
