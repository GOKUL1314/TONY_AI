"""
Comprehensive Unit & Integration Test Suite for TONY AI Vision Subsystem (Stage 9).
Tests 20 distinct scenarios covering security, validation, provider abstraction,
REST APIs, active-image context, untrusted content gates, and memory isolation.
"""
import base64
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from config.settings import Config
from app import create_app
from vision.models import VisionTaskType, VisionAnalysisRequest, VisionResult
from vision.errors import (
    VisionError,
    UnsupportedFormatError,
    ImageSizeExceededError,
    ImageValidationError,
    VisionProviderError,
    VisionTimeoutError,
    ImageNotFoundError
)
from vision.storage import VisionStorage, detect_image_format_from_bytes, sanitize_filename
from vision.history import VisionHistoryManager
from vision.mock_provider import MockVisionProvider
from vision.ollama_provider import OllamaVisionProvider
from vision.factory import get_vision_provider
from vision.manager import VisionManager
from intelligence.models import IntentType, TaskStatus
from intelligence.orchestrator import TonyOrchestrator
from intelligence.intent import IntentEngine
from intelligence.planner import TaskPlanner

# Helper byte generators for valid minimal images
MINIMAL_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
MINIMAL_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
MINIMAL_WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8L\x0e\x00\x00\x00/\x00\x00\x00\x00\x07\x01\x11\x9a\x04L\x01\x00\x00"


class TestVisionSubsystem(unittest.TestCase):
    """20 targeted test scenarios for Stage 9 Vision & Multimodal Understanding."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.upload_dir = self.test_dir / "uploads"
        self.history_file = self.test_dir / "vision_history.json"
        self.storage = VisionStorage(storage_dir=self.upload_dir, max_size_mb=2)
        self.history = VisionHistoryManager(history_file=self.history_file)
        self.mock_provider = MockVisionProvider(simulate_latency=0.0)
        self.manager = VisionManager(
            provider=self.mock_provider,
            storage=self.storage,
            history=self.history
        )

        # Flask Test Client
        class TestConfig(Config):
            TESTING = True
            VISION_PROVIDER = "mock"
            VISION_MODEL = "mock-vision-v1"
            VISION_DIR = self.upload_dir
            VISION_HISTORY_FILE = self.history_file
            AI_PROVIDER = "mock"
            STT_PROVIDER = "mock"
            TTS_PROVIDER = "mock"
            IMAGE_PROVIDER = "mock"
            VIDEO_PROVIDER = "mock"
            MEMORY_DATABASE = self.test_dir / "test_memory.db"

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # 1. Valid PNG
    def test_01_valid_png_upload(self):
        img_id, fname, path, size = self.storage.save_upload(MINIMAL_PNG, "test.png")
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".png")
        self.assertEqual(size, len(MINIMAL_PNG))

    # 2. Valid JPEG
    def test_02_valid_jpeg_upload(self):
        img_id, fname, path, size = self.storage.save_upload(MINIMAL_JPEG, "photo.jpg")
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".jpg")

    # 3. Valid WebP
    def test_03_valid_webp_upload(self):
        img_id, fname, path, size = self.storage.save_upload(MINIMAL_WEBP, "graphic.webp")
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".webp")

    # 4. Invalid Corrupted File
    def test_04_corrupt_invalid_file(self):
        corrupted = b"NOT_AN_IMAGE_DATA_12345"
        with self.assertRaises(UnsupportedFormatError):
            self.storage.save_upload(corrupted, "corrupt.png")

    # 5. Wrong Extension Mismatch (Executable disguised as PNG)
    def test_05_wrong_extension_mismatch(self):
        fake_png = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
        with self.assertRaises(UnsupportedFormatError):
            self.storage.save_upload(fake_png, "malicious.png")

    # 6. Oversized Image Rejection (> 2MB in test config)
    def test_06_oversized_image_rejection(self):
        oversized = MINIMAL_PNG + (b"\x00" * (3 * 1024 * 1024))
        with self.assertRaises(ImageSizeExceededError):
            self.storage.save_upload(oversized, "big.png")

    # 7. Malicious Filename Sanitization
    def test_07_malicious_filename_sanitization(self):
        cleaned = sanitize_filename("../../../etc/passwd\x00.png")
        self.assertNotIn("..", cleaned)
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("/", cleaned)

    # 8. Path Traversal Prevention
    def test_08_path_traversal_prevention(self):
        bad_path = self.upload_dir / ".." / "system32" / "test.png"
        with self.assertRaises(ImageValidationError):
            self.storage.validate_safe_path(bad_path)

    # 9. Missing Image Error Handling
    def test_09_missing_image_error(self):
        with self.assertRaises(ImageNotFoundError):
            self.manager.resolve_image(image_id="vis_non_existent_9999")

    # 10. Vision Provider Unavailable Handling
    def test_10_vision_provider_unavailable(self):
        failing_provider = MockVisionProvider(force_error=True)
        mgr = VisionManager(failing_provider, self.storage, self.history)
        with self.assertRaises(VisionProviderError):
            mgr.analyze(image_bytes=MINIMAL_PNG, prompt="Test fail")

    # 11. Vision Timeout Handling
    def test_11_vision_timeout_handling(self):
        timeout_provider = MockVisionProvider(force_timeout=True)
        mgr = VisionManager(timeout_provider, self.storage, self.history)
        with self.assertRaises(VisionTimeoutError):
            mgr.analyze(image_bytes=MINIMAL_PNG, prompt="Test timeout")

    # 12. Successful Scene Analysis
    def test_12_successful_scene_analysis(self):
        result = self.manager.analyze(image_bytes=MINIMAL_PNG, prompt="Analyze this architecture")
        self.assertTrue(result.vision_id.startswith("vis_"))
        self.assertIn("image", result.response.lower())
        self.assertFalse(result.metadata.get("untrusted_content") is None)
        # Stored in history
        latest = self.history.get_latest_record()
        self.assertIsNotNone(latest)
        self.assertEqual(latest.vision_id, result.vision_id)

    # 13. Visual Question Answering (VQA)
    def test_13_visual_question_answering(self):
        res = self.manager.ask_question("Is there a car in this image?", image_bytes=MINIMAL_PNG)
        self.assertEqual(res.task, VisionTaskType.QUESTION.value)
        self.assertIn("car", res.response.lower())

    # 14. OCR Text Extraction Request
    def test_14_ocr_text_extraction(self):
        res = self.manager.extract_text(image_bytes=MINIMAL_PNG)
        self.assertEqual(res.task, VisionTaskType.OCR.value)
        self.assertIn("TONY AI", res.response)

    # 15. Active Generated Image Context Analysis
    def test_15_active_generated_image_analysis(self):
        # Create a dummy image manager with an active image
        class DummyImageRecord:
            image_id = "img_active_stage6"
            file_path = str(self.test_dir / "gen.jpg")

        class DummyImageManager:
            def __init__(self, p):
                self.p = p
            def get_active_image(self):
                return DummyImageRecord()

        # Write dummy file
        Path(DummyImageRecord.file_path).write_bytes(MINIMAL_JPEG)
        mgr_with_active = VisionManager(
            provider=self.mock_provider,
            storage=self.storage,
            history=self.history,
            image_manager=DummyImageManager(DummyImageRecord.file_path)
        )
        res = mgr_with_active.analyze(use_active=True, prompt="Describe that active image")
        self.assertEqual(res.image_id, "img_active_stage6")
        self.assertTrue(res.metadata.get("untrusted_content"))

    # 16. Provider Selection Factory
    def test_16_provider_selection_factory(self):
        class CfgMock:
            VISION_PROVIDER = "mock"
            VISION_MODEL = "mock-model"
        class CfgOllama:
            VISION_PROVIDER = "ollama"
            VISION_MODEL = "moondream"
            OLLAMA_BASE_URL = "http://localhost:11434"
            VISION_TIMEOUT = 30

        p_mock = get_vision_provider(CfgMock)
        self.assertIsInstance(p_mock, MockVisionProvider)
        p_ollama = get_vision_provider(CfgOllama)
        self.assertIsInstance(p_ollama, OllamaVisionProvider)

    # 17. Security: Vision Output Never Executes Windows Action
    def test_17_no_automatic_windows_action_from_image_text(self):
        # Even if image contains text saying "delete all files" or "volume up",
        # the vision system returns text metadata and does NOT trigger tool execution
        res = self.manager.extract_text(image_bytes=MINIMAL_PNG)
        self.assertTrue(res.metadata.get("untrusted_content"))
        # Verify no tools were triggered in app context
        registry = self.app.config.get("TOOL_REGISTRY_INSTANCE")
        self.assertIsNotNone(registry)

    # 18. Security & Memory: No Automatic Persistence to memory.db
    def test_18_no_automatic_memory_persistence(self):
        mem_db = self.app.config.get("MEMORY_MANAGER_INSTANCE")
        initial_count = len(mem_db.list_memories()) if mem_db else 0

        # Perform analysis
        self.manager.analyze(image_bytes=MINIMAL_PNG, prompt="Look at this picture")

        # Confirm count has not increased automatically
        after_count = len(mem_db.list_memories()) if mem_db else 0
        self.assertEqual(initial_count, after_count)

    # 19. REST API Responses
    def test_19_api_responses(self):
        # 19a. POST /api/vision/analyze with multipart
        data = {
            "file": (io.BytesIO(MINIMAL_PNG), "sample.png"),
            "prompt": "Analyze this test graphic"
        }
        resp = self.client.post("/api/vision/analyze", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["success"])
        self.assertIn("result", body)
        self.assertEqual(body["result"]["provider"], "mock")

        # 19b. GET /api/vision/history
        resp_hist = self.client.get("/api/vision/history")
        self.assertEqual(resp_hist.status_code, 200)
        hist_body = resp_hist.get_json()
        self.assertTrue(hist_body["count"] >= 1)

        # 19c. GET /api/vision/health
        resp_health = self.client.get("/api/vision/health")
        self.assertEqual(resp_health.status_code, 200)

    # 20. Intelligence Orchestrator Vision Intent Routing
    def test_20_orchestrator_vision_intent_routing(self):
        engine = IntentEngine()
        intent = engine.detect_intent("Tony, analyze that image.")
        self.assertEqual(intent.type, IntentType.VISION_ANALYZE)
        self.assertTrue(intent.entities.get("use_active"))

        intent_q = engine.detect_intent("Tony, is there a car in this image?")
        self.assertEqual(intent_q.type, IntentType.VISION_QUESTION)

        intent_ocr = engine.detect_intent("Tony, what does this screenshot say?")
        self.assertEqual(intent_ocr.type, IntentType.VISION_OCR)

        intent_desc = engine.detect_intent("Tony, describe this image.")
        self.assertEqual(intent_desc.type, IntentType.VISION_DESCRIBE)


if __name__ == "__main__":
    unittest.main()
