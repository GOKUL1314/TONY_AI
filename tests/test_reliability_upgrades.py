"""
Targeted Regression Test Suite for TONY AI Reliability Upgrades:
1. Live Web Research Grounding & Anti-Fabrication Boundary
2. Contextual Fast-Path Reference Resolution (<5ms, zero LLM timeouts)
3. Local Model Timeout & Latency Resilience
4. Pollinations Image Generation Retries, Content-Filter Detection & Secret Protection
"""
import unittest
from unittest.mock import MagicMock, patch
import requests

from config.settings import Config
from app import create_app
from intelligence.target_scope import is_live_web_search_available, get_research_grounding_directive
from intelligence.reference_resolver import ReferenceResolver, ResolutionResult
from image_generation.pollinations_provider import PollinationsImageProvider
from image_generation.models import ImageGenerationRequest
from image_generation.errors import (
    ImageGenerationError,
    ProviderUnavailableError,
    RateLimitExceededError,
    SafetyViolationError
)
from image_generation.manager import ImageGenerationManager


class TestReliabilityConfig(Config):
    AI_PROVIDER = "mock"
    AI_MODEL = "tony-test-v1"
    IMAGE_PROVIDER = "mock"
    VIDEO_PROVIDER = "mock"
    STT_PROVIDER = "mock"
    TTS_PROVIDER = "mock"
    TESTING = True


class TestReliabilityUpgrades(unittest.TestCase):
    """Test suite validating the 3 reliability and grounding upgrades."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app(TestReliabilityConfig)
        cls.client = cls.app.test_client()

    # =========================================================================
    # PART 1: LIVE WEB RESEARCH GROUNDING TESTS
    # =========================================================================
    def test_01_live_web_search_capability_detected_as_unavailable(self):
        """Verify TONY accurately detects that live web search is not registered."""
        # Default registry without web_search
        registry = self.app.config.get("TOOL_REGISTRY_INSTANCE")
        self.assertFalse(is_live_web_search_available(registry))

        # Grounding directive must explicitly mandate unavailable status
        directive = get_research_grounding_directive(registry)
        self.assertIn("CURRENTLY UNAVAILABLE", directive)
        self.assertIn("NEVER claim you 'researched the web'", directive)
        self.assertIn("NEVER fabricate real-time ratings", directive)

    def test_02_research_prompt_does_not_invoke_search_files(self):
        """'Find me the best Python course.' must NOT invoke search_files."""
        res = self.client.post("/api/chat", json={"message": "Find me the best Python course."})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        reply = data.get("response", "")

        # Must not search local files
        self.assertNotIn("No files matching", reply)
        self.assertNotEqual(data.get("provider"), "tool_execution")

        # Must explicitly acknowledge live web search is unavailable and ground in internal knowledge
        self.assertIn("Live web search is currently unavailable", reply)
        self.assertIn("internal knowledge", reply)

        # Must NOT claim fake live ratings
        self.assertNotIn("4.8/5 on Coursera", reply)
        self.assertNotIn("4.9/5 on Udemy", reply)

    def test_03_research_and_planning_end_to_end_synthesis(self):
        """'Find me the best Python course and create a learning plan' multi-step pipeline."""
        res = self.client.post("/api/chat", json={"message": "TONY, find me the best Python course and create a learning plan"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        reply = data.get("response", "")

        # Multi-step plan execution
        plan_data = data.get("task_plan")
        self.assertIsNotNone(plan_data)
        self.assertEqual(plan_data.get("status"), "COMPLETED")

        # Both Step 1 (research) and Step 2 (planning) must complete
        steps = plan_data.get("steps", [])
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["action_type"], "research")
        self.assertEqual(steps[0]["status"], "COMPLETED")
        self.assertEqual(steps[1]["action_type"], "planning")
        self.assertEqual(steps[1]["status"], "COMPLETED")

        # Synthesized response includes course recommendations and learning plan
        self.assertIn("Python", reply)
        self.assertIn("learning plan", reply.lower())

    # =========================================================================
    # PART 2: CONTEXTUAL FAST-PATH REFERENCE RESOLUTION TESTS
    # =========================================================================
    def test_04_fast_path_resolves_known_platform_link(self):
        """'provide the coursera link' resolves in fast-path without invoking slow LLM."""
        history = [
            {"role": "user", "message": "Find me the best Python course."},
            {"role": "assistant", "message": "Based on internal knowledge, I recommend 'Python Crash Course' on Coursera and '100 Days of Code'."}
        ]

        result = ReferenceResolver.resolve("provide the coursera link", history)
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertFalse(result.ambiguous)
        self.assertEqual(result.url, "https://www.coursera.org")
        self.assertIn("https://www.coursera.org", result.response)
        self.assertIn("Coursera", result.response)

    def test_05_fast_path_detects_ambiguous_reference(self):
        """'give me the link' when multiple courses/platforms were discussed asks for clarification."""
        history = [
            {"role": "user", "message": "Recommend some programming courses."},
            {"role": "assistant", "message": "We have options on Coursera and Udemy to consider."}
        ]

        result = ReferenceResolver.resolve("give me the link", history)
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertTrue(result.ambiguous)
        self.assertIn("Which specific link would you like", result.response)
        self.assertIn("Coursera", result.response)
        self.assertIn("Udemy", result.response)

    def test_06_fast_path_recommendation_recall(self):
        """'what course did you recommend?' recalls previous courses without LLM."""
        history = [
            {"role": "user", "message": "Find me python tutorials"},
            {"role": "assistant", "message": "I recommended 'Python Crash Course' and 'Fluent Python' earlier."}
        ]

        result = ReferenceResolver.resolve("what course did you recommend?", history)
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertIn("Python Crash Course", result.response)
        self.assertIn("Fluent Python", result.response)

    def test_07_fast_path_via_chat_endpoint(self):
        """Verify chat endpoint serves fast-path requests directly."""
        # Prime conversation history with a turn mentioning Coursera
        conv_service = self.app.config.get("CONVERSATION_SERVICE_INSTANCE")
        conv_service.add_turn(
            "Find Python courses",
            "I recommend looking at Python for Everybody on Coursera."
        )

        res = self.client.post("/api/chat", json={"message": "provide the coursera link"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("provider"), "contextual_resolver")
        self.assertEqual(data.get("model"), "fast_path")
        self.assertIn("https://www.coursera.org", data.get("response"))

    # =========================================================================
    # PART 3: LOCAL MODEL TIMEOUT HANDLING TESTS
    # =========================================================================
    def test_08_local_model_timeout_graceful_handling(self):
        """Simulate Ollama 60s timeout: chat route returns polite response, not a broken 503."""
        from ai.provider import AIProviderError

        with patch("ai.mock_provider.MockProvider.generate_response", side_effect=AIProviderError("Local model inference timed out after 60s")):
            res = self.client.post("/api/chat", json={"message": "Write a 5000-word essay on AI"})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("timed_out"))
            self.assertIn("timed out", data.get("response"))
            self.assertIn("Sir", data.get("response"))

    # =========================================================================
    # PART 4: POLLINATIONS IMAGE GENERATION RELIABILITY & RETRY TESTS
    # =========================================================================
    @patch("requests.get")
    def test_09_pollinations_http_500_retries_and_succeeds(self, mock_get):
        """Pollinations transient 500 error is retried and succeeds on attempt 2."""
        # 1st attempt: 500, 2nd attempt: 200 valid JPEG
        mock_fail = MagicMock()
        mock_fail.status_code = 500
        mock_fail.text = "Internal Server Error"

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        # Valid JPEG header
        mock_ok.content = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
        mock_ok.headers = {"Content-Length": str(len(mock_ok.content))}

        mock_get.side_effect = [mock_fail, mock_ok]

        provider = PollinationsImageProvider(max_retries=2)
        req = ImageGenerationRequest(prompt="elephant drinking beer", width=512, height=512)

        data, meta = provider.generate_image(req)
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(meta["format"], "jpeg")
        self.assertTrue(len(data) > 0)

    @patch("requests.get")
    def test_10_pollinations_http_500_exhausts_retries_raises_provider_unavailable(self, mock_get):
        """Pollinations persistent 500 exhausts retries and raises ProviderUnavailableError."""
        mock_fail = MagicMock()
        mock_fail.status_code = 500
        mock_fail.text = "Cluster Outage"

        mock_get.return_value = mock_fail

        provider = PollinationsImageProvider(max_retries=1)
        req = ImageGenerationRequest(prompt="sunset over mountains")

        with self.assertRaises(ProviderUnavailableError):
            provider.generate_image(req)

        # Attempt 1 + 1 retry = 2 calls
        self.assertEqual(mock_get.call_count, 2)

    @patch("requests.get")
    def test_11_pollinations_content_filter_detection(self, mock_get):
        """Pollinations response containing content policy rejection raises SafetyViolationError, not 500."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Error: content filter triggered by prohibited content"

        mock_get.return_value = mock_resp

        provider = PollinationsImageProvider(max_retries=1)
        req = ImageGenerationRequest(prompt="some flagged prompt")

        with self.assertRaises(SafetyViolationError):
            provider.generate_image(req)

        # Safety violation should NOT retry
        self.assertEqual(mock_get.call_count, 1)

    @patch("requests.get")
    def test_12_pollinations_http_429_rate_limit_retry(self, mock_get):
        """Pollinations 429 rate limit is retried before raising RateLimitExceededError."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.text = "Too Many Requests"

        mock_get.return_value = mock_429

        provider = PollinationsImageProvider(max_retries=1)
        req = ImageGenerationRequest(prompt="a blue bird")

        with self.assertRaises(RateLimitExceededError):
            provider.generate_image(req)

        self.assertEqual(mock_get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
