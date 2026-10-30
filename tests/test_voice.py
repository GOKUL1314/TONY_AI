"""
Automated test suite for TONY Stage 2 Voice System.
Validates STT/TTS providers, transcription and synthesis endpoints,
error handling, and regression verification for Stage 1 chat and history.
"""
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from config.settings import Config
from app import create_app
from voice.stt_provider import get_stt_provider, STTProvider
from voice.tts_provider import get_tts_provider, TTSProvider
from voice.mock_stt_provider import MockSTTProvider
from voice.mock_tts_provider import MockTTSProvider


class TonyVoiceTestCase(unittest.TestCase):
    """Test suite covering Stage 2 Voice Input & Output."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        class VoiceTestConfig(Config):
            AI_PROVIDER = "mock"
            AI_MODEL = "tony-voice-test-v1"
            STT_PROVIDER = "mock"
            STT_MODEL = "mock-stt"
            TTS_PROVIDER = "mock"
            TTS_VOICE = "mock-voice"
            BASE_DIR = self.test_path
            DATA_DIR = self.test_path / "data"
            CONVERSATIONS_DIR = self.test_path / "data" / "conversations"
            AUDIO_DIR = self.test_path / "data" / "audio"
            LOGS_DIR = self.test_path / "logs"
            TESTING = True

        self.config = VoiceTestConfig
        self.app = create_app(config_class=VoiceTestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_voice_status_endpoint(self):
        """Verify GET /api/voice/status returns STT and TTS health diagnostics."""
        res = self.client.get("/api/voice/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "online")
        self.assertIn("stt", data)
        self.assertIn("tts", data)
        self.assertTrue(data["stt"]["available"])
        self.assertTrue(data["tts"]["available"])

    def test_stt_provider_initialization(self):
        """Verify STT provider factory instantiates an STTProvider."""
        provider = get_stt_provider(self.config)
        self.assertIsInstance(provider, STTProvider)
        health = provider.check_health()
        self.assertTrue(health["available"])

    def test_tts_provider_initialization(self):
        """Verify TTS provider factory instantiates a TTSProvider."""
        provider = get_tts_provider(self.config)
        self.assertIsInstance(provider, TTSProvider)
        health = provider.check_health()
        self.assertTrue(health["available"])

    def test_tts_synthesis_file_generation(self):
        """Verify TTS provider generates a valid audio file."""
        provider = get_tts_provider(self.config)
        output_file = self.test_path / "data" / "audio" / "test_synth.wav"
        result_path = provider.synthesize("Hello from TONY voice engine", output_file)
        self.assertTrue(result_path.exists())
        self.assertGreater(result_path.stat().st_size, 40)

    def test_transcribe_missing_audio_payload(self):
        """Verify POST /api/voice/transcribe rejects requests with no audio."""
        res = self.client.post("/api/voice/transcribe")
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    def test_transcribe_empty_audio_file(self):
        """Verify POST /api/voice/transcribe rejects empty (0-byte) audio files."""
        data = {
            "audio": (io.BytesIO(b""), "empty.wav")
        }
        res = self.client.post(
            "/api/voice/transcribe",
            data=data,
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("empty", data["error"].lower())

    def test_transcribe_valid_audio_multipart(self):
        """Verify POST /api/voice/transcribe accepts valid audio and returns transcription."""
        data = {
            "audio": (io.BytesIO(b"RIFFdummywavecontentforstttesting"), "mic_test.wav")
        }
        res = self.client.post(
            "/api/voice/transcribe",
            data=data,
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertIn("text", json_data)
        self.assertIn("provider", json_data)
        self.assertEqual(json_data["text"], "Hello Tony")

    def test_speak_endpoint_valid_text(self):
        """Verify POST /api/voice/speak synthesizes text into audio/wav stream."""
        payload = {"text": "Good evening. How can I assist you?"}
        res = self.client.post("/api/voice/speak", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "audio/wav")
        self.assertGreater(len(res.data), 40)

    def test_speak_endpoint_empty_text(self):
        """Verify POST /api/voice/speak rejects empty text payload."""
        payload = {"text": "   "}
        res = self.client.post("/api/voice/speak", json=payload)
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    def test_speak_endpoint_missing_text(self):
        """Verify POST /api/voice/speak rejects payload missing 'text' field."""
        payload = {"wrong_key": "some text"}
        res = self.client.post("/api/voice/speak", json=payload)
        self.assertEqual(res.status_code, 400)

    def test_stage1_chat_regression(self):
        """Verify existing /api/chat still operates seamlessly with voice extensions loaded."""
        res = self.client.post("/api/chat", json={"message": "Testing Stage 1 compatibility"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("response", data)

    def test_stage1_history_regression(self):
        """Verify existing conversation persistence functions correctly alongside voice."""
        # 1. Post message
        self.client.post("/api/chat", json={"message": "Save this message"})
        # 2. Check history
        res = self.client.get("/api/history")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["history"][0]["user_message"], "Save this message")


if __name__ == "__main__":
    unittest.main()
