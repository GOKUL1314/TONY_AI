"""
Automated test suite for TONY AI assistant.
Validates Flask endpoints, input validation, conversation history, and provider handling.
"""
import unittest
from pathlib import Path
import tempfile
import shutil

from config.settings import Config
from app import create_app
from ai.mock_provider import MockProvider
from ai.local_provider import LocalProvider
from ai.provider import AIProviderError


class TonyTestCase(unittest.TestCase):
    """Test suite covering core TONY API and services."""

    def setUp(self):
        # Create temporary directory for tests to isolate storage
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        class TestConfig(Config):
            AI_PROVIDER = "mock"
            AI_MODEL = "tony-test-v1"
            BASE_DIR = self.test_path
            DATA_DIR = self.test_path / "data"
            CONVERSATIONS_DIR = self.test_path / "data" / "conversations"
            LOGS_DIR = self.test_path / "logs"
            TESTING = True

        self.config = TestConfig
        self.app = create_app(config_class=TestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        # Clean up temporary test files
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_homepage(self):
        """Verify homepage renders successfully with TONY branding."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"TONY", response.data)
        self.assertIn(b"PERSONAL AI DESKTOP ASSISTANT", response.data)

    def test_chat_valid_message(self):
        """Verify valid chat request receives structured response and updates history."""
        payload = {"message": "Hello Tony"}
        response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertIn("response", data)
        self.assertIn("timestamp", data)
        self.assertIn("provider", data)
        self.assertIn("Good evening. I'm Tony. How can I assist you?", data["response"])

    def test_chat_personality_capabilities(self):
        """Verify TONY answers capability questions accurately for Stage 1."""
        payload = {"message": "What can you do?"}
        response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("I can help you with questions, coding, research, planning", data["response"])

    def test_chat_empty_message(self):
        """Verify empty message is rejected with HTTP 400."""
        payload = {"message": "   "}
        response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("empty", data["error"].lower())

    def test_chat_missing_message_field(self):
        """Verify payload without message field is rejected with HTTP 400."""
        payload = {"wrong_key": "Hello"}
        response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)

    def test_chat_non_json_payload(self):
        """Verify non-JSON payload is rejected with HTTP 400."""
        response = self.client.post(
            "/api/chat",
            data="plain text message",
            content_type="text/plain"
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)

    def test_conversation_history_persistence(self):
        """Verify conversation turns are stored and can be retrieved."""
        # 1. Send first message
        self.client.post("/api/chat", json={"message": "First message"})
        # 2. Send second message
        self.client.post("/api/chat", json={"message": "Second message"})

        # 3. Retrieve history
        res = self.client.get("/api/history")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["count"], 2)
        turns = data["history"]
        self.assertEqual(turns[0]["user_message"], "First message")
        self.assertEqual(turns[1]["user_message"], "Second message")

    def test_clear_conversation_history(self):
        """Verify history can be cleared."""
        # Add message
        self.client.post("/api/chat", json={"message": "To be cleared"})
        res1 = self.client.get("/api/history")
        self.assertEqual(res1.get_json()["count"], 1)

        # Clear
        del_res = self.client.delete("/api/history")
        self.assertEqual(del_res.status_code, 200)

        # Verify now empty
        res2 = self.client.get("/api/history")
        self.assertEqual(res2.get_json()["count"], 0)

    def test_system_status_endpoint(self):
        """Verify /api/status returns telemetry and provider diagnostics."""
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "online")
        self.assertGreaterEqual(data["stage"], 1)
        self.assertIn("provider", data)

    def test_local_provider_connection_error_handling(self):
        """Verify LocalProvider gracefully handles offline Ollama server."""
        offline_provider = LocalProvider(
            model_name="llama3.2:1b",
            base_url="http://127.0.0.1:9999",  # Non-existent port
            timeout=1
        )
        with self.assertRaises(AIProviderError) as ctx:
            offline_provider.generate_response("Hello")
        self.assertIn("Unable to connect to local Ollama server", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
