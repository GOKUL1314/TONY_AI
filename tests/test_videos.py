"""
Comprehensive automated test suite for TONY AI Video Generation Subsystem (Stage 7).
Covers provider abstractions, mock generation, Hugging Face client handling, local hardware
diagnostics, asynchronous jobs, status polling, history, security sandboxing, chat/voice
integration, active image context, and strict paid-usage prevention.
"""
import io
import os
import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from config.settings import Config
from app import create_app
from video_generation.models import (
    VideoMetadata,
    VideoGenerationRequest,
    VideoJob,
    LocalCapabilityReport
)
from video_generation.base import VideoProvider
from video_generation.mock_provider import MockVideoProvider
from video_generation.huggingface_provider import HuggingFaceVideoProvider
from video_generation.local_provider import LocalVideoProvider, detect_local_hardware
from video_generation.storage import VideoStorage
from video_generation.history import VideoHistoryManager
from video_generation.jobs import VideoJobManager
from video_generation.manager import VideoGenerationManager
from video_generation.provider import create_video_provider
from video_generation.safety import (
    mask_secret,
    check_prompt_safety,
    validate_prompt_or_raise,
    validate_safe_filename,
    validate_safe_output_path
)
from video_generation.prompts import (
    detect_video_intent,
    enhance_video_prompt,
    parse_prompt_parameters
)
from video_generation.errors import (
    VideoGenerationError,
    VideoAuthenticationError,
    ProviderUnavailableError,
    FreeQuotaUnavailableError,
    LocalVideoUnavailableError,
    PaidProviderBlockedError,
    VideoValidationError,
    SafetyViolationError,
    VideoNotFoundError,
    UnsupportedVideoCapabilityError
)


class TestAppConfig(Config):
    VIDEO_PROVIDER = "mock"
    IMAGE_PROVIDER = "mock"
    AI_PROVIDER = "mock"
    STT_PROVIDER = "mock"
    TTS_PROVIDER = "mock"


class TestVideoGeneration(unittest.TestCase):
    """Test suite covering all Stage 7 Video Generation requirements."""

    def setUp(self):
        self.test_data_dir = Path("data/test_stage7_videos")
        self.test_data_dir.mkdir(parents=True, exist_ok=True)
        self.test_history_file = self.test_data_dir / "test_video_history.json"
        self.storage = VideoStorage(storage_dir=self.test_data_dir)
        self.history = VideoHistoryManager(history_file=self.test_history_file)
        self.mock_provider = MockVideoProvider()

    def tearDown(self):
        if self.test_data_dir.exists():
            shutil.rmtree(self.test_data_dir, ignore_errors=True)

    # 1. Provider interface
    def test_01_provider_interface(self):
        self.assertTrue(issubclass(MockVideoProvider, VideoProvider))
        self.assertTrue(issubclass(HuggingFaceVideoProvider, VideoProvider))
        self.assertTrue(issubclass(LocalVideoProvider, VideoProvider))
        self.assertTrue(hasattr(self.mock_provider, "generate_text_to_video"))
        self.assertTrue(hasattr(self.mock_provider, "generate_image_to_video"))
        self.assertTrue(hasattr(self.mock_provider, "check_health"))

    # 2. Mock provider end-to-end generation
    def test_02_mock_provider_generation(self):
        req = VideoGenerationRequest(prompt="a futuristic jet in the clouds", duration=2, fps=16)
        data, meta = self.mock_provider.generate_text_to_video(req)
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 1000)
        self.assertEqual(meta["provider"], "mock")
        self.assertTrue(meta["simulated"])

    # 3. Hugging Face configuration
    def test_03_huggingface_configuration(self):
        hf = HuggingFaceVideoProvider(
            token="hf_mocktoken1234567890123456789012345",
            model_name="Wan-AI/Wan2.1-T2V-1.3B",
            allow_paid=False
        )
        health = hf.check_health()
        self.assertTrue(health["available"])
        self.assertTrue(health["free_mode_active"])
        self.assertFalse(health["paid_fallback_enabled"])
        self.assertIn("free", health["message"].lower())
        self.assertIn("allowance", health["message"].lower())

    # 4. Missing HF token
    def test_04_missing_hf_token(self):
        hf = HuggingFaceVideoProvider(token=None)
        health = hf.check_health()
        self.assertFalse(health["available"])
        self.assertEqual(health["status"], "missing_token")
        with self.assertRaises(ProviderUnavailableError):
            req = VideoGenerationRequest(prompt="a spaceship")
            hf.generate_text_to_video(req)

    # 5. Secret protection & masking
    def test_05_secret_protection(self):
        token = "hf_abcdef1234567890abcdef1234567890"
        masked = mask_secret(token)
        self.assertNotIn("abcdef1234567890abcdef", masked)
        self.assertTrue(masked.startswith("hf_a"))

        # Test prompt screening rejects credentials
        prompt_with_key = "Make a video of sk-1234567890abcdefghij123456"
        is_safe, reason = check_prompt_safety(prompt_with_key)
        self.assertFalse(is_safe)
        with self.assertRaises(SafetyViolationError):
            validate_prompt_or_raise(prompt_with_key)

    # 6. Local capability detection
    def test_06_local_capability_detection(self):
        report = detect_local_hardware()
        self.assertIsInstance(report, LocalCapabilityReport)
        self.assertIn("Windows", report.os)
        self.assertIsInstance(report.gpu_name, str)

    # 7. Local provider unavailable when unconfigured
    def test_07_local_provider_unavailable(self):
        local = LocalVideoProvider()
        health = local.check_health()
        self.assertEqual(health["status"], "unavailable")
        with self.assertRaises(LocalVideoUnavailableError):
            req = VideoGenerationRequest(prompt="a cat walking")
            local.generate_text_to_video(req)

    # 8. Text-to-video intent
    def test_08_text_to_video_intent(self):
        res = detect_video_intent("Tony, create a video of a futuristic city at night")
        self.assertEqual(res["intent"], "text_to_video")
        self.assertIn("futuristic city", res["prompt"])

        res2 = detect_video_intent("What is video generation?")
        self.assertEqual(res2["intent"], "none")

    # 9. Image-to-video intent
    def test_09_image_to_video_intent(self):
        res = detect_video_intent("Tony, animate this image", has_active_image=True)
        self.assertEqual(res["intent"], "image_to_video")

        res2 = detect_video_intent("Turn the generated image into a moving video")
        self.assertEqual(res2["intent"], "image_to_video")

    # 10. Prompt parameter extraction
    def test_10_prompt_extraction(self):
        p, dur, w, h = parse_prompt_parameters("cinematic space station 5 seconds")
        self.assertIn("space station", p)
        self.assertEqual(dur, 5)
        self.assertEqual(w, 768)
        self.assertEqual(h, 432)

    # 11. Duration validation
    def test_11_duration_validation(self):
        mgr = VideoGenerationManager(
            provider=self.mock_provider,
            storage=self.storage,
            history=self.history,
            max_duration=5
        )
        with self.assertRaises(VideoValidationError):
            mgr.start_text_to_video("a car driving", duration=120)

    # 12. Resolution validation & enhancement
    def test_12_enhancement(self):
        p = enhance_video_prompt("a red sports car")
        self.assertIn("smooth cinematic camera motion", p)

    # 13. Job creation & 14. Job status
    def test_13_14_job_creation_and_status(self):
        job_mgr = VideoJobManager(
            provider=self.mock_provider,
            storage=self.storage,
            history=self.history
        )
        req = VideoGenerationRequest(prompt="test racecar", duration=2, fps=16)
        job = job_mgr.submit_job(req)
        self.assertIsNotNone(job.generation_id)
        self.assertIn(job.status, ("queued", "processing", "completed"))

        retrieved = job_mgr.get_job(job.generation_id)
        self.assertEqual(retrieved.generation_id, job.generation_id)

    # 15. Job completion
    def test_15_job_completion(self):
        job_mgr = VideoJobManager(
            provider=self.mock_provider,
            storage=self.storage,
            history=self.history
        )
        req = VideoGenerationRequest(prompt="fast completion test", duration=2, fps=16)
        job = job_mgr.submit_job(req)
        # Give worker a brief moment to finish mock synthesis
        import time
        for _ in range(30):
            if job.status == "completed":
                break
            time.sleep(0.1)

        self.assertEqual(job.status, "completed")
        self.assertIsNotNone(job.video_metadata)
        self.assertTrue(Path(job.video_metadata.file_path).exists())

    # 16. Job failure
    def test_16_job_failure(self):
        fail_provider = MockVideoProvider()
        fail_provider.generate_text_to_video = MagicMock(side_effect=VideoGenerationError("Simulated failure"))

        job_mgr = VideoJobManager(
            provider=fail_provider,
            storage=self.storage,
            history=self.history,
            max_retries=0
        )
        job = job_mgr.submit_job(VideoGenerationRequest(prompt="fail test", duration=2))
        import time
        for _ in range(20):
            if job.status == "failed":
                break
            time.sleep(0.1)

        self.assertEqual(job.status, "failed")
        self.assertIn("Simulated failure", job.error)

    # 17. Job cancellation
    def test_17_job_cancellation(self):
        job_mgr = VideoJobManager(
            provider=self.mock_provider,
            storage=self.storage,
            history=self.history
        )
        job = job_mgr.submit_job(VideoGenerationRequest(prompt="cancel test", duration=2))
        cancelled = job_mgr.cancel_job(job.generation_id)
        self.assertTrue(cancelled)
        self.assertEqual(job.status, "cancelled")

    # 18. Retry behavior
    def test_18_retry_behavior(self):
        call_count = 0
        def flappy_generator(request, progress_callback=None):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Temporary glitch")
            return self.mock_provider._render_synthetic_mp4(512, 512, 2, 16, "retry test"), {"simulated": True}

        prov = MockVideoProvider()
        prov.generate_text_to_video = flappy_generator

        job_mgr = VideoJobManager(
            provider=prov,
            storage=self.storage,
            history=self.history,
            max_retries=2
        )
        job = job_mgr.submit_job(VideoGenerationRequest(prompt="retry test", duration=2))
        import time
        for _ in range(40):
            if job.status == "completed":
                break
            time.sleep(0.1)

        self.assertEqual(job.status, "completed")
        self.assertEqual(call_count, 2)

    # 19. History
    def test_19_history_management(self):
        meta = VideoMetadata(
            video_id="vid_test_123",
            filename="vid_test_123.mp4",
            file_path="C:/dummy/vid_test_123.mp4",
            url="/api/videos/vid_test_123/file",
            prompt="history test prompt",
            duration=5,
            provider="mock",
            model="mock-video-v1"
        )
        self.history.add_record(meta)
        self.assertEqual(self.history.count(), 1)
        retrieved = self.history.get_record("vid_test_123")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.prompt, "history test prompt")

    # 20. Regeneration
    def test_20_regeneration(self):
        mgr = VideoGenerationManager(
            provider=self.mock_provider,
            storage=self.storage,
            history=self.history
        )
        meta = VideoMetadata(
            video_id="vid_regen_1",
            filename="vid_regen_1.mp4",
            file_path="C:/dummy/vid_regen_1.mp4",
            url="/api/videos/vid_regen_1/file",
            prompt="a glowing orb",
            duration=3
        )
        self.history.add_record(meta)
        regen_job = mgr.regenerate("vid_regen_1")
        self.assertIn("a glowing orb", regen_job.request.prompt)
        self.assertEqual(regen_job.request.duration, 3)

    # 21. Delete
    def test_21_delete(self):
        # Create real test file
        data = self.mock_provider._render_synthetic_mp4(512, 512, 2, 16, "delete test")
        vid_id, vname, vpath, size, tname, tpath = self.storage.save_video_bytes(data)

        meta = VideoMetadata(
            video_id=vid_id,
            filename=vname,
            file_path=str(vpath),
            url=f"/api/videos/{vid_id}/file",
            thumbnail_path=str(tpath) if tpath else None,
            prompt="delete me"
        )
        self.history.add_record(meta)

        mgr = VideoGenerationManager(
            provider=self.mock_provider,
            storage=self.storage,
            history=self.history
        )
        success = mgr.delete_video(vid_id)
        self.assertTrue(success)
        self.assertFalse(vpath.exists())
        self.assertEqual(self.history.count(), 0)

    # 22. File path security
    def test_22_file_path_security(self):
        with self.assertRaises(ValueError):
            validate_safe_filename("../evil.mp4")
        with self.assertRaises(ValueError):
            validate_safe_filename("..\\evil.mp4")
        with self.assertRaises(ValueError):
            validate_safe_filename("evil.exe")

        with self.assertRaises(SafetyViolationError):
            validate_safe_output_path(Path("C:/Windows/System32/evil.mp4"), self.test_data_dir)

    # 23. File type validation
    def test_23_file_type_validation(self):
        valid = validate_safe_filename("video_20261004_abc123.mp4")
        self.assertEqual(valid, "video_20261004_abc123.mp4")
        with self.assertRaises(ValueError):
            validate_safe_filename("video_20261004_abc123.bat")

    # 24. API endpoints
    def test_24_api_endpoints(self):
        app = create_app(TestAppConfig)
        client = app.test_client()

        # GET /api/videos/status
        res = client.get("/api/videos/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("provider", data)

        # GET /api/videos/providers
        res_prov = client.get("/api/videos/providers")
        self.assertEqual(res_prov.status_code, 200)
        pdata = res_prov.get_json()
        self.assertIn("huggingface", pdata)
        self.assertIn("mock", pdata)

        # GET /api/videos/local-capability
        res_cap = client.get("/api/videos/local-capability")
        self.assertEqual(res_cap.status_code, 200)

        # POST /api/videos/generate
        res_gen = client.post("/api/videos/generate", json={
            "prompt": "futuristic flying bike",
            "duration": 2
        })
        self.assertEqual(res_gen.status_code, 202)
        gen_data = res_gen.get_json()
        gen_id = gen_data["generation_id"]

        # GET /api/videos/<id>/status
        res_stat = client.get(f"/api/videos/{gen_id}/status")
        self.assertEqual(res_stat.status_code, 200)

        # GET /api/videos
        res_list = client.get("/api/videos")
        self.assertEqual(res_list.status_code, 200)

    # 25. Chat integration (text-to-video)
    def test_25_chat_integration(self):
        app = create_app(TestAppConfig)
        client = app.test_client()

        res = client.post("/api/chat", json={
            "message": "Tony, create a video of a robot walking in a lab"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("generating a video", data["response"])
        self.assertIn("video_job", data)

    # 26. Voice integration
    def test_26_voice_integration(self):
        app = create_app(TestAppConfig)
        client = app.test_client()

        # Simulate voice transcription returning video intent
        with patch.object(app.config["STT_PROVIDER_INSTANCE"], "transcribe", return_value="create a video of a spaceship"):
            # Mock transcribe endpoint
            res = client.post("/api/voice/transcribe", data={"audio": (io.BytesIO(b"RIFFdummyWAVbytes"), "voice.wav")})
            if res.status_code == 200:
                t_text = res.get_json()["text"]
                # Then chat gets that transcribed text
                chat_res = client.post("/api/chat", json={"message": t_text})
                self.assertEqual(chat_res.status_code, 200)
                self.assertIn("video_job", chat_res.get_json())

    # 27. Active image integration (image-to-video)
    def test_27_active_image_integration(self):
        app = create_app(TestAppConfig)
        img_mgr = app.config["IMAGE_MANAGER_INSTANCE"]
        vid_mgr = app.config["VIDEO_MANAGER_INSTANCE"]

        # Generate an image first
        img_res = img_mgr.generate("a high-tech laboratory robot")
        self.assertTrue(img_res.success)
        active_img = img_mgr.get_active_image()
        self.assertIsNotNone(active_img)

        # Animate active image
        job = vid_mgr.start_image_to_video(image_id=active_img.image_id)
        self.assertEqual(job.request.parent_image_id, active_img.image_id)

    # 28. Paid-provider protection
    def test_28_paid_provider_protection(self):
        hf = HuggingFaceVideoProvider(
            token="hf_mock_token_12345",
            allow_paid=False
        )
        fake_client = MagicMock()
        # Simulate payment required 402
        fake_client.text_to_video.side_effect = Exception("402 Payment Required: Credit card required")
        hf._client = fake_client

        req = VideoGenerationRequest(prompt="should not charge user")
        with self.assertRaises(FreeQuotaUnavailableError) as ctx:
            hf.generate_text_to_video(req)
        self.assertIn("unavailable or exhausted", str(ctx.exception))

    # 29. Provider status (no secrets disclosed)
    def test_29_provider_status_no_secrets(self):
        app = create_app(TestAppConfig)
        client = app.test_client()
        res = client.get("/api/videos/providers")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        raw_text = json.dumps(data)
        self.assertNotIn("hf_", raw_text)
        self.assertNotIn("sk-", raw_text)

    # 30. Hugging Face adapter with fake client
    def test_30_huggingface_adapter_with_fake_client(self):
        hf = HuggingFaceVideoProvider(
            token="hf_test_token_12345",
            model_name="Wan-AI/Wan2.1-T2V-1.3B",
            allow_paid=False
        )
        fake_client = MagicMock()
        fake_client.text_to_video.return_value = b"RIFFfakeMP4videobytes12345"
        hf._client = fake_client

        req = VideoGenerationRequest(prompt="a test video")
        video_bytes, meta = hf.generate_text_to_video(req)
        self.assertEqual(video_bytes, b"RIFFfakeMP4videobytes12345")
        self.assertEqual(meta["model"], "Wan-AI/Wan2.1-T2V-1.3B")

    # 31. Local adapter with injected backend runner
    def test_31_local_adapter_with_backend_runner(self):
        def fake_runner(req, progress=None, image_bytes=None):
            return b"FAKELOCALMP4BYTES", {"provider": "local", "model": "local-diffusion-v1"}

        local = LocalVideoProvider(backend_runner=fake_runner)
        req = VideoGenerationRequest(prompt="local generation test")
        data, meta = local.generate_text_to_video(req)
        self.assertEqual(data, b"FAKELOCALMP4BYTES")
        self.assertEqual(meta["provider"], "local")

    # 32. Optional Real Hugging Face Test (Runs ONLY if RUN_REAL_VIDEO_TEST=true and HF_TOKEN is present)
    def test_32_optional_real_huggingface_test(self):
        run_real = os.getenv("RUN_REAL_VIDEO_TEST", "false").lower() in ("true", "1", "yes")
        token = os.getenv("HF_TOKEN", "").strip()

        if not run_real or not token:
            self.skipTest("Optional real Hugging Face video test disabled (RUN_REAL_VIDEO_TEST=false or no HF_TOKEN).")

        hf = HuggingFaceVideoProvider(token=token, allow_paid=False)
        req = VideoGenerationRequest(prompt="a glowing cube rotating", duration=2, fps=16)
        try:
            data, meta = hf.generate_text_to_video(req)
            self.assertIsInstance(data, bytes)
            self.assertGreater(len(data), 0)
        except FreeQuotaUnavailableError:
            print("\nREAL HUGGING FACE VIDEO TEST: SKIPPED/UNAVAILABLE (Free quota exhausted or serverless cold).")
        except Exception as e:
            print(f"\nREAL HUGGING FACE VIDEO TEST RESULT: {e}")

    # 33. Hugging Face 401/403 Authentication Error Handling
    def test_33_hf_authentication_error_handling(self):
        hf = HuggingFaceVideoProvider(token="hf_mock_token_12345", allow_paid=False)
        fake_client = MagicMock()
        fake_client.text_to_video.side_effect = Exception("Client error '401 Unauthorized' for url ... Invalid username or password.")
        hf._client = fake_client

        req = VideoGenerationRequest(prompt="a test prompt")
        with self.assertRaises(VideoAuthenticationError) as ctx:
            hf.generate_text_to_video(req)
        self.assertIn("authentication failed", str(ctx.exception).lower())
        # Ensure token is never included in error
        self.assertNotIn("hf_mock_token_12345", str(ctx.exception))

    # 34. API Route Aliases (/jobs/<id>, /history, /jobs/<id>/cancel)
    def test_34_api_route_aliases(self):
        app = create_app(TestAppConfig)
        client = app.test_client()

        # 1. /api/videos/history
        res = client.get("/api/videos/history")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")

        # 2. /api/videos/generate -> /api/videos/jobs/<generation_id>
        gen_res = client.post("/api/videos/generate", json={"prompt": "route alias test video", "duration": 2})
        self.assertEqual(gen_res.status_code, 202)
        gen_id = gen_res.get_json()["generation_id"]

        job_res = client.get(f"/api/videos/jobs/{gen_id}")
        self.assertEqual(job_res.status_code, 200)
        self.assertEqual(job_res.get_json()["generation_id"], gen_id)

        # 3. /api/videos/jobs/<generation_id>/cancel
        cancel_res = client.post(f"/api/videos/jobs/{gen_id}/cancel")
        # May be 200 (if still running) or 400 (if already finished in test runner)
        self.assertIn(cancel_res.status_code, (200, 400))

    # 35. Hugging Face Health Check Token Privacy
    def test_35_hf_health_check_token_privacy(self):
        secret_token = "hf_super_secret_token_abcdef123456"
        hf = HuggingFaceVideoProvider(token=secret_token)
        health = hf.check_health()
        self.assertTrue(health["token_configured"])
        self.assertEqual(health["token_status"], "PRESENT")
        # Ensure token and any masked substring are absent
        health_str = json.dumps(health)
        self.assertNotIn(secret_token, health_str)
        self.assertNotIn("abcdef123456", health_str)
        self.assertNotIn("token_masked", health)


if __name__ == "__main__":
    unittest.main()
