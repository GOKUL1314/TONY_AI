"""
Comprehensive Automated Test Suite for TONY AI Image Generation Subsystem (Stage 6).
Tests prompt safety, intent detection, prompt refinement, deterministic mock generation,
disk storage sandboxing, persistent metadata history, high-level manager orchestration,
REST API endpoints, and chat pipeline integration.
"""
import unittest
import tempfile
import shutil
import json
from pathlib import Path

from unittest.mock import patch, MagicMock
import requests

from config.settings import Config
from app import create_app
from image_generation.models import (
    ImageMetadata,
    ImageGenerationRequest,
    ImageEditRequest,
    ImageGenerationResult
)
from image_generation.errors import (
    ImageGenerationError,
    ProviderUnavailableError,
    RateLimitExceededError,
    SafetyViolationError,
    InvalidPromptError,
    ImageNotFoundError
)
from image_generation.safety import (
    check_prompt_safety,
    validate_prompt_or_raise,
    validate_safe_filename,
    validate_safe_output_path
)
from image_generation.prompts import (
    detect_image_intent,
    merge_edit_prompt,
    enhance_prompt,
    clean_conversational_text
)
from image_generation.mock_provider import MockImageProvider, create_synthetic_png
from image_generation.pollinations_provider import PollinationsImageProvider
from image_generation.provider import get_image_provider
from image_generation.storage import ImageStorage
from image_generation.history import ImageHistoryManager
from image_generation.manager import ImageGenerationManager


class TestImageSafetyAndGuardrails(unittest.TestCase):
    """Tests safety filters, secret protection, and path sandboxing."""

    def test_safe_prompts_pass(self):
        safe_prompts = [
            "a futuristic cyberpunk city at twilight",
            "a realistic portrait of a helpful AI assistant",
            "a red sports car driving in the rain with neon reflections",
            "an Iron Man-inspired futuristic technology laboratory"
        ]
        for p in safe_prompts:
            is_safe, reason = check_prompt_safety(p)
            self.assertTrue(is_safe, f"Safe prompt '{p}' was incorrectly rejected: {reason}")
            cleaned = validate_prompt_or_raise(p)
            self.assertEqual(cleaned, p)

    def test_prohibited_content_blocked(self):
        unsafe_prompts = [
            "generate nsfw adult pornography illustration",
            "create explicit erotic nude photo",
            "make image of gore mutilation and blood bath",
            "draw a bomb making guide with explosives"
        ]
        for p in unsafe_prompts:
            is_safe, reason = check_prompt_safety(p)
            self.assertFalse(is_safe, f"Unsafe prompt '{p}' should have been rejected.")
            with self.assertRaises(SafetyViolationError):
                validate_prompt_or_raise(p)

    def test_sensitive_credentials_blocked(self):
        secret_prompts = [
            "create an image with sk-proj1234567890abcdef1234567890",
            "generate a picture showing password='SuperSecretPassword123!'",
            "draw image with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdefghijk",
            "illustration containing -----BEGIN RSA PRIVATE KEY----- MIIEowIBAAKCAQ"
        ]
        for p in secret_prompts:
            is_safe, reason = check_prompt_safety(p)
            self.assertFalse(is_safe, f"Prompt containing credential was not blocked: {p}")
            self.assertIn("credential", reason.lower())
            with self.assertRaises(SafetyViolationError):
                validate_prompt_or_raise(p)

    def test_filename_sandboxing(self):
        # Valid filenames
        self.assertEqual(validate_safe_filename("tony_img_20261004_123456.png"), "tony_img_20261004_123456.png")
        self.assertEqual(validate_safe_filename("test-image_01.png"), "test-image_01.png")

        # Invalid filenames
        invalid_filenames = [
            "../secret.png",
            "..\\windows\\system32.png",
            "image/sub/test.png",
            "image.jpg",  # only png allowed
            "test\x00evil.png",
            "test;rm -rf.png"
        ]
        for fn in invalid_filenames:
            with self.assertRaises(ValueError):
                validate_safe_filename(fn)

    def test_output_path_sandboxing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            valid_path = base_dir / "tony_img_001.png"
            resolved = validate_safe_output_path(valid_path, base_dir)
            self.assertEqual(resolved, valid_path.resolve())

            # Attempt path traversal escaping base directory
            traversal_path = base_dir / ".." / "evil.png"
            with self.assertRaises(SafetyViolationError):
                validate_safe_output_path(traversal_path, base_dir)


class TestImagePromptsAndIntent(unittest.TestCase):
    """Tests natural language intent detection, prompt extraction, and follow-up merging."""

    def test_creation_intent_detection(self):
        samples = [
            ("Tony, create an image of a futuristic city.", "a futuristic city"),
            ("Tony, generate a cinematic Iron Man-inspired laboratory.", "Iron Man-inspired laboratory"),
            ("Create a realistic portrait of a futuristic AI assistant.", "a futuristic AI assistant"),
            ("Generate an image of a red sports car in the rain.", "a red sports car in the rain"),
            ("Hey Tony, please draw a picture of a cozy mountain cabin", "a cozy mountain cabin"),
            ("make a wallpaper of deep space galaxies", "deep space galaxies"),
            ("picture of a cybernetic dragon", "a cybernetic dragon")
        ]
        for text, expected_prompt in samples:
            intent_data = detect_image_intent(text, has_active_image=False)
            self.assertEqual(intent_data["intent"], "create", f"Failed for '{text}'")
            self.assertIn(expected_prompt.lower(), intent_data["prompt"].lower())

    def test_edit_intent_detection(self):
        samples = [
            ("Tony, make the previous image more cinematic.", "more cinematic"),
            ("Make it nighttime in the rain", "nighttime in the rain"),
            ("make this darker with neon lighting", "darker with neon lighting"),
            ("add rain to the image", "rain"),
            ("change the background to a starry night sky", "a starry night sky")
        ]
        for text, expected_inst in samples:
            intent_data = detect_image_intent(text, has_active_image=True)
            self.assertEqual(intent_data["intent"], "edit", f"Failed edit intent for '{text}'")
            self.assertIn(expected_inst.lower(), intent_data["instruction"].lower())

    def test_regeneration_intent_detection(self):
        samples = [
            "Tony, regenerate the previous image.",
            "regenerate the last image",
            "remake that image",
            "try again",
            "generate another one"
        ]
        for text in samples:
            intent_data = detect_image_intent(text, has_active_image=True)
            self.assertEqual(intent_data["intent"], "regenerate", f"Failed regen intent for '{text}'")

    def test_non_image_conversations_ignored(self):
        non_image_turns = [
            "What is the capital of France?",
            "Can you write a python script to sort a list?",
            "What time is it right now?",
            "Remember that my favorite color is cyan",
            "Open Notepad please",
            "How are you doing today, Tony?"
        ]
        for turn in non_image_turns:
            intent_data = detect_image_intent(turn, has_active_image=True)
            self.assertEqual(intent_data["intent"], "none", f"Incorrectly detected image intent for: '{turn}'")

    def test_prompt_merger(self):
        base = "a red sports car in the rain"
        inst = "make it nighttime with neon reflections"
        merged = merge_edit_prompt(base, inst)
        self.assertIn("a red sports car in the rain", merged)
        self.assertIn("nighttime with neon reflections", merged)

    def test_prompt_enhancement(self):
        simple = "a futuristic city"
        enhanced = enhance_prompt(simple)
        self.assertIn("a futuristic city", enhanced)
        self.assertIn("lighting", enhanced)

        already_detailed = "a futuristic city, 8k resolution, cinematic lighting, photorealistic octane render"
        self.assertEqual(enhance_prompt(already_detailed), already_detailed)


class TestMockImageProvider(unittest.TestCase):
    """Tests deterministic offline PNG generator."""

    def test_synthetic_png_validity(self):
        png_bytes = create_synthetic_png(width=128, height=128, seed_str="test-city")
        self.assertIsInstance(png_bytes, bytes)
        self.assertGreater(len(png_bytes), 100)

        # Standard PNG magic signature: \x89PNG\r\n\x1a\n
        png_signature = b"\x89PNG\r\n\x1a\n"
        self.assertTrue(png_bytes.startswith(png_signature))
        self.assertIn(b"IHDR", png_bytes)
        self.assertIn(b"IDAT", png_bytes)
        self.assertIn(b"IEND", png_bytes)

    def test_mock_provider_generation(self):
        provider = MockImageProvider(model_name="mock-image-v1")
        req = ImageGenerationRequest(prompt="a futuristic laboratory", width=256, height=256)
        png_bytes, meta = provider.generate_image(req)

        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(meta["provider"], "mock")
        self.assertEqual(meta["model"], "mock-image-v1")
        self.assertTrue(meta["simulated"])

    def test_mock_provider_health(self):
        provider = MockImageProvider()
        health = provider.check_health()
        self.assertTrue(health["available"])
        self.assertEqual(health["status"], "ready")


class TestImageStorageAndHistory(unittest.TestCase):
    """Tests safe disk persistence and metadata tracking."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_dir = Path(self.temp_dir) / "images"
        self.history_file = Path(self.temp_dir) / "history.json"
        self.storage = ImageStorage(storage_dir=self.storage_dir)
        self.history = ImageHistoryManager(history_file=self.history_file, max_records=5)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_storage_save_and_retrieve(self):
        raw_bytes = create_synthetic_png(64, 64, "storage-test")
        img_id, filename, file_path, size = self.storage.save_image_bytes(raw_bytes)

        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.stat().st_size, size)

        retrieved_path = self.storage.get_image_path(filename)
        self.assertIsNotNone(retrieved_path)
        self.assertEqual(retrieved_path, file_path)

        # Delete image
        self.assertTrue(self.storage.delete_image_file(filename))
        self.assertFalse(file_path.exists())

    def test_history_crud(self):
        meta1 = ImageMetadata(
            image_id="img_1",
            filename="tony_img_1.png",
            file_path="/tmp/tony_img_1.png",
            url="/api/images/img_1/file",
            prompt="futuristic city"
        )
        meta2 = ImageMetadata(
            image_id="img_2",
            filename="tony_img_2.png",
            file_path="/tmp/tony_img_2.png",
            url="/api/images/img_2/file",
            prompt="red sports car"
        )

        self.history.add_record(meta1)
        self.assertEqual(self.history.count(), 1)
        self.assertEqual(self.history.get_latest_record().image_id, "img_1")

        self.history.add_record(meta2)
        self.assertEqual(self.history.count(), 2)
        self.assertEqual(self.history.get_latest_record().image_id, "img_2")

        # Get specific record
        rec = self.history.get_record("img_1")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.prompt, "futuristic city")

        # Delete record
        self.assertTrue(self.history.delete_record("img_1"))
        self.assertEqual(self.history.count(), 1)
        self.assertIsNone(self.history.get_record("img_1"))


class TestImageGenerationManager(unittest.TestCase):
    """Tests high-level orchestration, edit branching, and regeneration."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = ImageStorage(storage_dir=Path(self.temp_dir) / "images")
        self.history = ImageHistoryManager(history_file=Path(self.temp_dir) / "history.json")
        self.provider = MockImageProvider(model_name="mock-test-v1")
        self.manager = ImageGenerationManager(
            provider=self.provider,
            storage=self.storage,
            history=self.history,
            enhance_prompts=True
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_image(self):
        res = self.manager.generate("a tranquil Japanese zen garden")
        self.assertTrue(res.success)
        self.assertIsNotNone(res.image_metadata)
        self.assertEqual(self.manager.active_image_id, res.image_metadata.image_id)
        self.assertTrue(Path(res.image_metadata.file_path).exists())

    def test_edit_image_flow(self):
        # 1. Generate base image
        res1 = self.manager.generate("a red sports car")
        self.assertTrue(res1.success)
        base_id = res1.image_metadata.image_id

        # 2. Refine image referencing active context
        res2 = self.manager.edit("more cinematic in the rain")
        self.assertTrue(res2.success)
        self.assertNotEqual(res2.image_metadata.image_id, base_id)
        self.assertEqual(res2.image_metadata.parent_image_id, base_id)
        self.assertIn("a red sports car", res2.image_metadata.prompt)
        self.assertIn("in the rain", res2.image_metadata.prompt)

    def test_regenerate_image_flow(self):
        res1 = self.manager.generate("a cinematic mountain sunset")
        self.assertTrue(res1.success)

        res_regen = self.manager.regenerate()
        self.assertTrue(res_regen.success)
        self.assertEqual(res_regen.image_metadata.prompt, "a cinematic mountain sunset")

    def test_delete_image_flow(self):
        res = self.manager.generate("to be deleted")
        img_id = res.image_metadata.image_id

        self.assertTrue(self.manager.delete_image(img_id))
        self.assertIsNone(self.manager.get_image(img_id))
        self.assertIsNone(self.manager.get_image_file_path(img_id))


class TestImageRESTAPI(unittest.TestCase):
    """Tests the /api/images/* REST endpoints."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_path = Path(self.temp_dir)

        class TestConfig(Config):
            AI_PROVIDER = "mock"
            BASE_DIR = self.test_path
            DATA_DIR = self.test_path / "data"
            IMAGE_DIR = self.test_path / "data" / "generated_images"
            IMAGE_HISTORY_FILE = self.test_path / "data" / "image_history.json"
            IMAGE_PROVIDER = "mock"
            IMAGE_MODEL = "mock-api-test"
            LOGS_DIR = self.test_path / "logs"
            TESTING = True

        self.app = create_app(config_class=TestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_endpoint_success(self):
        payload = {"prompt": "a futuristic cyber city"}
        res = self.client.post("/api/images/generate", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("image", data)
        self.assertEqual(data["image"]["prompt"], "a futuristic cyber city")
        self.assertTrue(data["image"]["url"].startswith("/api/images/"))

    def test_generate_endpoint_invalid_payload(self):
        # Empty prompt
        res1 = self.client.post("/api/images/generate", json={"prompt": "   "})
        self.assertEqual(res1.status_code, 400)

        # Non-json
        res2 = self.client.post("/api/images/generate", data="text", content_type="text/plain")
        self.assertEqual(res2.status_code, 400)

    def test_generate_endpoint_safety_rejection(self):
        res = self.client.post("/api/images/generate", json={"prompt": "create explicit adult nsfw pornography"})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    def test_list_and_get_details(self):
        # Generate 2 images
        self.client.post("/api/images/generate", json={"prompt": "image one"})
        res2 = self.client.post("/api/images/generate", json={"prompt": "image two"})
        img2_id = res2.get_json()["image"]["image_id"]

        # List
        list_res = self.client.get("/api/images")
        self.assertEqual(list_res.status_code, 200)
        data = list_res.get_json()
        self.assertEqual(data["count"], 2)

        # Details
        detail_res = self.client.get(f"/api/images/{img2_id}")
        self.assertEqual(detail_res.status_code, 200)
        detail_data = detail_res.get_json()
        self.assertEqual(detail_data["image"]["prompt"], "image two")

    def test_serve_image_file(self):
        gen_res = self.client.post("/api/images/generate", json={"prompt": "viewable image"})
        img_id = gen_res.get_json()["image"]["image_id"]

        file_res = self.client.get(f"/api/images/{img_id}/file")
        self.assertEqual(file_res.status_code, 200)
        self.assertEqual(file_res.content_type, "image/png")
        self.assertTrue(file_res.data.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_edit_endpoint(self):
        gen_res = self.client.post("/api/images/generate", json={"prompt": "a red sports car"})
        img_id = gen_res.get_json()["image"]["image_id"]

        edit_res = self.client.post(f"/api/images/{img_id}/edit", json={"instruction": "make it in the rain"})
        self.assertEqual(edit_res.status_code, 201)
        data = edit_res.get_json()
        self.assertEqual(data["image"]["parent_image_id"], img_id)
        self.assertIn("in the rain", data["image"]["prompt"])

    def test_regenerate_endpoint(self):
        gen_res = self.client.post("/api/images/generate", json={"prompt": "a futuristic robot"})
        img_id = gen_res.get_json()["image"]["image_id"]

        regen_res = self.client.post(f"/api/images/{img_id}/regenerate")
        self.assertEqual(regen_res.status_code, 201)
        data = regen_res.get_json()
        self.assertEqual(data["image"]["prompt"], "a futuristic robot")

    def test_delete_endpoint(self):
        gen_res = self.client.post("/api/images/generate", json={"prompt": "temporary image"})
        img_id = gen_res.get_json()["image"]["image_id"]

        del_res = self.client.delete(f"/api/images/{img_id}")
        self.assertEqual(del_res.status_code, 200)

        # Verify 404 after deletion
        get_res = self.client.get(f"/api/images/{img_id}")
        self.assertEqual(get_res.status_code, 404)

    def test_status_endpoint(self):
        res = self.client.get("/api/images/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["stage"], 6)
        self.assertEqual(data["status"], "ready")


class TestChatImageIntegration(unittest.TestCase):
    """Tests natural language image generation through /api/chat."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_path = Path(self.temp_dir)

        class TestConfig(Config):
            AI_PROVIDER = "mock"
            BASE_DIR = self.test_path
            DATA_DIR = self.test_path / "data"
            IMAGE_DIR = self.test_path / "data" / "generated_images"
            IMAGE_HISTORY_FILE = self.test_path / "data" / "image_history.json"
            IMAGE_PROVIDER = "mock"
            IMAGE_MODEL = "mock-chat-v1"
            LOGS_DIR = self.test_path / "logs"
            TESTING = True

        self.app = create_app(config_class=TestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_chat_triggers_image_generation(self):
        payload = {"message": "Tony, create an image of a futuristic city."}
        res = self.client.post("/api/chat", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(data["provider"], "image_generation")
        self.assertIn("image_result", data)
        self.assertIn("I've generated an image of a futuristic city", data["response"])
        self.assertTrue(data["image_result"]["url"].startswith("/api/images/"))

    def test_chat_triggers_image_followup_edit(self):
        # 1. Create first image
        self.client.post("/api/chat", json={"message": "Generate an image of a red sports car in the rain."})

        # 2. Refine previous image
        edit_payload = {"message": "Tony, make the previous image more cinematic."}
        res = self.client.post("/api/chat", json=edit_payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(data["provider"], "image_generation")
        self.assertIn("image_result", data)
        self.assertIn("I've updated the image", data["response"])
        self.assertIsNotNone(data["image_result"]["parent_image_id"])

    def test_chat_triggers_image_regeneration(self):
        # 1. Create image
        self.client.post("/api/chat", json={"message": "Tony, generate a cinematic Iron Man-inspired laboratory."})

        # 2. Regenerate
        regen_payload = {"message": "Tony, regenerate the previous image."}
        res = self.client.post("/api/chat", json=regen_payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(data["provider"], "image_generation")
        self.assertIn("I've regenerated the image for you", data["response"])

    def test_chat_safety_rejection(self):
        payload = {"message": "Create an image of nsfw pornography"}
        res = self.client.post("/api/chat", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("I couldn't generate that image", data["response"])

    def test_normal_chat_not_intercepted(self):
        payload = {"message": "What is the theory of relativity?"}
        res = self.client.post("/api/chat", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("mock", data["provider"].lower())
        self.assertNotIn("image_result", data)


class TestPollinationsImageProvider(unittest.TestCase):
    """Unit tests for PollinationsImageProvider with mocked HTTP responses."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = ImageStorage(Path(self.temp_dir) / "images")
        self.history = ImageHistoryManager(Path(self.temp_dir) / "history.json")
        self.provider = PollinationsImageProvider(model_name="flux", timeout=10)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_provider_health(self):
        health = self.provider.check_health()
        self.assertTrue(health["available"])
        self.assertEqual(health["provider"], "pollinations")
        self.assertEqual(health["model"], "flux")
        self.assertEqual(health["status"], "ready")
        self.assertFalse(health["simulated"])

    def test_factory_selection(self):
        class ConfigPollinations:
            IMAGE_PROVIDER = "pollinations"
            IMAGE_MODEL = "flux"

        class ConfigFlux:
            IMAGE_PROVIDER = "flux"
            IMAGE_MODEL = "turbo"

        class ConfigMock:
            IMAGE_PROVIDER = "mock"
            IMAGE_MODEL = "mock-model"

        p1 = get_image_provider(ConfigPollinations)
        self.assertIsInstance(p1, PollinationsImageProvider)
        self.assertEqual(p1.model_name, "flux")

        p2 = get_image_provider(ConfigFlux)
        self.assertIsInstance(p2, PollinationsImageProvider)
        self.assertEqual(p2.model_name, "turbo")

        p3 = get_image_provider(ConfigMock)
        self.assertIsInstance(p3, MockImageProvider)

    @patch("requests.get")
    def test_successful_real_image_response(self, mock_get):
        synthetic_png = create_synthetic_png(128, 128, "test")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = synthetic_png
        mock_response.headers = {"Content-Length": str(len(synthetic_png))}
        mock_get.return_value = mock_response

        req = ImageGenerationRequest(prompt="a futuristic skyline", width=1024, height=1024)
        raw_bytes, meta = self.provider.generate_image(req)

        self.assertEqual(raw_bytes, synthetic_png)
        self.assertEqual(meta["provider"], "pollinations")
        self.assertEqual(meta["model"], "flux")
        self.assertEqual(meta["format"], "png")
        self.assertFalse(meta["simulated"])
        self.assertGreater(meta["generation_time_ms"], -1)

    def test_empty_prompt_rejection(self):
        req = ImageGenerationRequest(prompt="   ")
        with self.assertRaises(InvalidPromptError):
            self.provider.generate_image(req)

    @patch("requests.get")
    def test_timeout_handling(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")
        req = ImageGenerationRequest(prompt="a futuristic skyline")
        with self.assertRaises(ImageGenerationError) as ctx:
            self.provider.generate_image(req)
        self.assertEqual(ctx.exception.status_code, 504)
        self.assertIn("timed out", str(ctx.exception).lower())

    @patch("requests.get")
    def test_connection_error_handling(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("Name resolution failed")
        req = ImageGenerationRequest(prompt="a futuristic skyline")
        with self.assertRaises(ProviderUnavailableError):
            self.provider.generate_image(req)

    @patch("requests.get")
    def test_rate_limiting_429(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        req = ImageGenerationRequest(prompt="a futuristic skyline")
        with self.assertRaises(RateLimitExceededError):
            self.provider.generate_image(req)

    @patch("requests.get")
    def test_http_failures(self, mock_get):
        # 503 Service Unavailable
        mock_resp_503 = MagicMock()
        mock_resp_503.status_code = 503
        mock_get.return_value = mock_resp_503
        with self.assertRaises(ProviderUnavailableError):
            self.provider.generate_image(ImageGenerationRequest(prompt="city"))

        # 400 Bad Request
        mock_resp_400 = MagicMock()
        mock_resp_400.status_code = 400
        mock_get.return_value = mock_resp_400
        with self.assertRaises(ImageGenerationError) as ctx:
            self.provider.generate_image(ImageGenerationRequest(prompt="city"))
        self.assertEqual(ctx.exception.status_code, 400)

        # 500 Internal Error
        mock_resp_500 = MagicMock()
        mock_resp_500.status_code = 500
        mock_get.return_value = mock_resp_500
        with self.assertRaises(ImageGenerationError) as ctx:
            self.provider.generate_image(ImageGenerationRequest(prompt="city"))
        self.assertEqual(ctx.exception.status_code, 500)

    @patch("requests.get")
    def test_invalid_non_image_response(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><body>Bad Gateway 502</body></html>"
        mock_response.headers = {}
        mock_get.return_value = mock_response
        with self.assertRaises(ImageGenerationError) as ctx:
            self.provider.generate_image(ImageGenerationRequest(prompt="city"))
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("non-image", str(ctx.exception).lower())

    @patch("requests.get")
    def test_oversized_response(self, mock_get):
        provider = PollinationsImageProvider(max_response_size=100)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"A" * 200
        mock_response.headers = {"Content-Length": "200"}
        mock_get.return_value = mock_response
        with self.assertRaises(ImageGenerationError) as ctx:
            provider.generate_image(ImageGenerationRequest(prompt="city"))
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("exceeded maximum", str(ctx.exception).lower())

    @patch("requests.get")
    def test_no_silent_fallback_to_mock_on_failure(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("Server unreachable")
        manager = ImageGenerationManager(
            provider=self.provider,
            storage=self.storage,
            history=self.history
        )
        result = manager.generate("city skyline")
        # CRITICAL REQUIREMENT: Must NOT fall back to mock
        self.assertFalse(result.success)
        self.assertIsNone(result.image_metadata)
        self.assertIn("connection error", result.error_message.lower())
        # Zero mock images should be stored
        self.assertEqual(self.history.count(), 0)

    @patch("requests.get")
    def test_manager_success_with_pollinations(self, mock_get):
        synthetic_png = create_synthetic_png(128, 128, "pollinations-test")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = synthetic_png
        mock_response.headers = {"Content-Length": str(len(synthetic_png))}
        mock_get.return_value = mock_response

        manager = ImageGenerationManager(
            provider=self.provider,
            storage=self.storage,
            history=self.history
        )
        result = manager.generate("futuristic Hyderabad skyline")
        self.assertTrue(result.success)
        self.assertIsNotNone(result.image_metadata)
        self.assertEqual(result.image_metadata.provider, "pollinations")
        self.assertEqual(result.image_metadata.model, "flux")
        self.assertFalse(result.image_metadata.simulated)
        self.assertTrue(Path(result.image_metadata.file_path).is_file())


if __name__ == "__main__":
    unittest.main()
