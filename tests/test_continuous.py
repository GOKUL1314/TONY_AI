"""
Automated test suite for TONY Stage 3: Continuous Conversation & Hands-Free System.
Validates WakeWordDetector, VAD energy calculation, wake-check endpoint,
configuration toggles, safety states, and regression testing for Stages 1 & 2.
"""
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from config.settings import Config
from app import create_app
from voice.wake_word import WakeWordDetector
from voice.vad import VoiceActivityDetector, VADConfig


class TonyContinuousTestCase(unittest.TestCase):
    """Test suite covering Stage 3 continuous hands-free dialogue features."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        class ContinuousTestConfig(Config):
            AI_PROVIDER = "mock"
            AI_MODEL = "tony-continuous-test-v1"
            STT_PROVIDER = "mock"
            STT_MODEL = "mock-stt"
            TTS_PROVIDER = "mock"
            TTS_VOICE = "mock-voice"
            CONTINUOUS_MODE = True
            WAKE_WORD_ENABLED = True
            WAKE_WORD = "hey tony"
            VOICE_SILENCE_TIMEOUT = 1.2
            MICROPHONE_ENABLED = True
            AUDIO_DUCKING = True
            BASE_DIR = self.test_path
            DATA_DIR = self.test_path / "data"
            CONVERSATIONS_DIR = self.test_path / "data" / "conversations"
            AUDIO_DIR = self.test_path / "data" / "audio"
            LOGS_DIR = self.test_path / "logs"
            TESTING = True

        self.config = ContinuousTestConfig
        self.app = create_app(config_class=ContinuousTestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # 1. Wake-Word Detector Unit Tests
    def test_wake_word_detector_hey_tony(self):
        """Verify WakeWordDetector recognizes 'Hey Tony' with trailing prompt."""
        detector = WakeWordDetector()
        detected, phrase, trailing = detector.detect("Hey Tony, explain quantum physics")
        self.assertTrue(detected)
        self.assertEqual(phrase.lower(), "hey tony")
        self.assertEqual(trailing, "explain quantum physics")

    def test_wake_word_detector_single_name_tony(self):
        """Verify WakeWordDetector recognizes single name 'Tony'."""
        detector = WakeWordDetector()
        detected, phrase, trailing = detector.detect("Tony what time is it")
        self.assertTrue(detected)
        self.assertIn("tony", phrase.lower())
        self.assertEqual(trailing, "what time is it")

    def test_wake_word_detector_wake_only(self):
        """Verify WakeWordDetector identifies when only the wake phrase was spoken."""
        detector = WakeWordDetector()
        detected, phrase, trailing = detector.detect("Hey Tony!")
        self.assertTrue(detected)
        self.assertEqual(trailing, "")
        self.assertTrue(detector.is_wake_word_only("Hey Tony!"))

    def test_wake_word_detector_no_wake_phrase(self):
        """Verify WakeWordDetector does not false-positive on other words."""
        detector = WakeWordDetector()
        detected, phrase, trailing = detector.detect("Good morning assistant")
        self.assertFalse(detected)
        self.assertEqual(trailing, "Good morning assistant")

    def test_wake_word_detector_tony_primary_and_yes_sir(self):
        """Verify 'Tony' is the primary wake word and responds with 'Yes, Sir.'."""
        detector = WakeWordDetector(primary_phrase="tony")
        self.assertEqual(detector.primary_phrase, "tony")
        self.assertEqual(detector.get_wake_response(), "Yes, Sir.")

        # Test "Tony!" without "Hey"
        detected, phrase, trailing = detector.detect("Tony! What time is it?")
        self.assertTrue(detected)
        self.assertEqual(phrase.lower(), "tony")
        self.assertEqual(trailing, "What time is it?")

        # Test "Tony?"
        detected, phrase, trailing = detector.detect("Tony?")
        self.assertTrue(detected)
        self.assertEqual(trailing, "")
        self.assertTrue(detector.is_wake_word_only("Tony?"))

        # Test "Okay Tony"
        detected, phrase, trailing = detector.detect("Okay Tony, create an image")
        self.assertTrue(detected)
        self.assertEqual(phrase.lower(), "okay tony")
        self.assertEqual(trailing, "create an image")

    def test_wake_word_confidence_threshold(self):
        """Verify wake detector rejects low-confidence audio transcripts."""
        detector = WakeWordDetector(confidence_threshold=0.65)
        # Below threshold
        detected, _, _ = detector.detect("Tony what time is it", confidence=0.45)
        self.assertFalse(detected)
        # Above threshold
        detected, _, _ = detector.detect("Tony what time is it", confidence=0.85)
        self.assertTrue(detected)

    def test_wake_word_cooldown_debounce(self):
        """Verify rapid repeated trigger from same audio segment is debounced."""
        detector = WakeWordDetector(cooldown_ms=2000)
        # First trigger succeeds
        detected1, _, _ = detector.detect("Tony!")
        self.assertTrue(detected1)
        # Immediate second trigger is debounced
        detected2, _, _ = detector.detect("Tony!")
        self.assertFalse(detected2)

    def test_wake_word_active_conversation_retention(self):
        """Verify active conversation allows subsequent turns without repeating wake word."""
        detector = WakeWordDetector()
        # In active conversation, command without "Tony" is accepted
        detected, phrase, trailing = detector.detect("Make it darker", is_active_conversation=True)
        self.assertTrue(detected)
        self.assertEqual(phrase, "active_conversation")
        self.assertEqual(trailing, "Make it darker")

    # 2. VAD Engine Unit Tests
    def test_vad_rms_calculation_silence(self):
        """Verify VAD calculates near-zero RMS for silent PCM audio."""
        vad = VoiceActivityDetector(VADConfig(energy_threshold=0.015))
        # 1600 bytes of silence (800 16-bit PCM 0 samples)
        silent_pcm = b"\x00" * 1600
        rms = vad.calculate_rms(silent_pcm)
        self.assertEqual(rms, 0.0)
        self.assertFalse(vad.is_speech(silent_pcm))

    def test_vad_rms_calculation_loud_signal(self):
        """Verify VAD detects vocal energy when samples exceed threshold."""
        vad = VoiceActivityDetector(VADConfig(energy_threshold=0.015))
        # Synthesize 16-bit PCM wave with high amplitude
        import struct
        samples = [15000 if i % 2 == 0 else -15000 for i in range(800)]
        loud_pcm = struct.pack(f"<{len(samples)}h", *samples)
        rms = vad.calculate_rms(loud_pcm)
        self.assertGreater(rms, 0.2)
        self.assertTrue(vad.is_speech(loud_pcm))

    # 3. Wake-Check REST Endpoint Tests
    def test_api_wake_check_detected(self):
        """Verify POST /api/voice/wake-check returns wake detection structure."""
        res = self.client.post("/api/voice/wake-check", json={"text": "Hey Tony write a test"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["detected"])
        self.assertEqual(data["wake_phrase"].lower(), "hey tony")
        self.assertEqual(data["trailing_prompt"], "write a test")
        self.assertFalse(data["wake_only"])

    def test_api_wake_check_wake_only(self):
        """Verify POST /api/voice/wake-check detects wake-only prompt."""
        res = self.client.post("/api/voice/wake-check", json={"text": "Hey Tony"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["detected"])
        self.assertTrue(data["wake_only"])

    def test_api_wake_check_invalid_payload(self):
        """Verify POST /api/voice/wake-check validates payload."""
        res = self.client.post("/api/voice/wake-check", json={})
        self.assertEqual(res.status_code, 400)

    # 4. Voice Config Endpoint Tests (Continuous Mode & Silence Timeout)
    def test_api_voice_config_get(self):
        """Verify GET /api/voice/config returns Stage 3 settings."""
        res = self.client.get("/api/voice/config")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["continuous_mode"])
        self.assertTrue(data["wake_word_enabled"])
        self.assertEqual(data["voice_silence_timeout"], 1.2)
        self.assertTrue(data["microphone_enabled"])

    def test_api_voice_config_post_update(self):
        """Verify POST /api/voice/config updates settings dynamically."""
        res = self.client.post(
            "/api/voice/config",
            json={
                "continuous_mode": False,
                "voice_silence_timeout": 1.5,
                "microphone_enabled": False
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["continuous_mode"])
        self.assertEqual(data["voice_silence_timeout"], 1.5)
        self.assertFalse(data["microphone_enabled"])

    # 5. Regression Verification (Stage 1 & Stage 2)
    def test_regression_chat_still_functional(self):
        """Ensure POST /api/chat operates without regression."""
        res = self.client.post("/api/chat", json={"message": "Stage 3 regression check"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("response", data)

    def test_regression_conversation_history(self):
        """Ensure dialogue persistence functions properly."""
        self.client.post("/api/chat", json={"message": "First message"})
        res = self.client.get("/api/history")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["count"], 1)

    def test_regression_transcribe_endpoint(self):
        """Ensure POST /api/voice/transcribe remains operational."""
        data = {"audio": (io.BytesIO(b"RIFFdummywavecontent"), "test.wav")}
        res = self.client.post("/api/voice/transcribe", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text", res.get_json())

    def test_regression_speak_endpoint(self):
        """Ensure POST /api/voice/speak remains operational."""
        res = self.client.post("/api/voice/speak", json={"text": "Speech synthesis active"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "audio/wav")


if __name__ == "__main__":
    unittest.main()
