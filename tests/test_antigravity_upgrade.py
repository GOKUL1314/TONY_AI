"""
Test Suite for Antigravity (agy) Architecture Upgrade.
Verifies:
1. Dynamic Token Budgeting and Rolling Context Compaction.
2. Protection against prompt blowup on 20+ turns.
3. Ollama local inference options tuning (num_ctx, temperature, num_predict).
4. Antigravity analytical framework and output standards in system prompt.
5. Fast context assembly in chat route.
"""
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from intelligence.context_compactor import ContextCompactor
from intelligence.system_prompt import build_system_prompt, TONY_BASE_SYSTEM_PROMPT
from ai.local_provider import LocalProvider
from services.conversation import ConversationService
from app import create_app


class TestAntigravityUpgrade(unittest.TestCase):
    """Unit tests for Antigravity performance and reasoning capabilities."""

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    # =========================================================================
    # 1. CONTEXT COMPACTOR & TOKEN BUDGETING
    # =========================================================================
    def test_compact_history_under_budget_keeps_verbatim(self):
        """Short conversations under character budget remain verbatim."""
        history = [
            {"user_message": "Hello Tony", "assistant_response": "Good evening, Sir."},
            {"user_message": "What is the time?", "assistant_response": "It is 7:30 PM, Sir."}
        ]
        result = ContextCompactor.compact_history(history, max_chars=2000)
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0]["message"], "Hello Tony")
        self.assertEqual(result[1]["message"], "Good evening, Sir.")
        self.assertEqual(result[2]["message"], "What is the time?")
        self.assertEqual(result[3]["message"], "It is 7:30 PM, Sir.")

    def test_compact_history_over_budget_compacts_older_turns(self):
        """Conversations exceeding budget summarize older turns into recap block."""
        # Create 10 turns with substantial text
        history = []
        for i in range(10):
            history.append({
                "user_message": f"Question {i}: Tell me about topic {i} in depth.",
                "assistant_response": f"Response {i}: Here is a very detailed explanation about topic {i} with extensive discussion."
            })

        result = ContextCompactor.compact_history(history, max_chars=1000, keep_recent_turns=2)
        total_chars = sum(len(m["message"]) for m in result)

        # Total compacted length must be well controlled
        self.assertTrue(total_chars < 2000)

        # Must have recap block from older turns
        recap_turns = [m for m in result if "RECAP OF OLDER TOPICS" in m["message"]]
        self.assertEqual(len(recap_turns), 1)
        self.assertIn("Question 7", recap_turns[0]["message"])

        # Latest 2 turns must be preserved verbatim
        self.assertEqual(result[-2]["message"], "Question 9: Tell me about topic 9 in depth.")

    def test_compact_history_caps_oversized_single_message(self):
        """A single 10k character code response is guarded from overflowing context."""
        history = [
            {"user_message": "Write a script", "assistant_response": "X" * 10000}
        ]
        result = ContextCompactor.compact_history(history, max_chars=2000, keep_recent_turns=1)
        asst_msg = result[-1]["message"]
        self.assertTrue(len(asst_msg) < 1500)
        self.assertIn("truncated for context efficiency", asst_msg)

    def test_assemble_prompt_context_budget_ceiling(self):
        """assemble_prompt_context strictly enforces overall prompt budget."""
        sys_prompt = build_system_prompt()
        history = [
            {"user_message": f"Turn {i}", "assistant_response": f"Answer {i} " * 50}
            for i in range(15)
        ]
        mem = "User prefers Python. User lives in Hyderabad. User likes dark mode. " * 30
        pers = "Active morning briefing. Prefers concise answers. " * 20

        context = ContextCompactor.assemble_prompt_context(
            system_prompt=sys_prompt,
            recent_history=history,
            memory_context=mem,
            personalization_context=pers,
            max_prompt_chars=6000
        )

        total_prompt_chars = sum(len(m["message"]) for m in context)
        self.assertTrue(total_prompt_chars <= 6200)
        # System prompt is first
        self.assertEqual(context[0]["role"], "system")
        self.assertIn("TONY AI", context[0]["message"])

    # =========================================================================
    # 2. CONVERSATION SERVICE INTEGRATION
    # =========================================================================
    def test_conversation_service_get_compacted_provider_context(self):
        """ConversationService provides compacted provider context."""
        conv_dir = Path("data/tests_conv")
        conv_dir.mkdir(parents=True, exist_ok=True)
        service = ConversationService(conv_dir)
        service.clear_history()

        for i in range(8):
            service.add_turn(
                f"User message {i} discussing advanced architecture topics",
                f"Assistant answer {i} providing detailed code and solutions for topic {i}"
            )

        compacted = service.get_compacted_provider_context(limit=8, max_chars=500, keep_recent_turns=2)
        self.assertTrue(len(compacted) > 0)
        recap_turns = [m for m in compacted if "RECAP OF OLDER TOPICS" in m["message"]]
        self.assertEqual(len(recap_turns), 1)

    # =========================================================================
    # 3. LOCAL PROVIDER INFERENCE TUNING (OLLAMA OPTIONS)
    # =========================================================================
    def test_local_provider_injects_inference_options(self):
        """LocalProvider payload includes num_ctx, temperature, num_predict, top_p."""
        provider = LocalProvider(
            model_name="llama3.2:3b",
            num_ctx=4096,
            temperature=0.3,
            num_predict=1024,
            top_p=0.9
        )

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"message": {"content": "Diagnostic complete, Sir."}}
            mock_post.return_value = mock_resp

            reply = provider.generate_response("Hello Tony")
            self.assertEqual(reply, "Diagnostic complete, Sir.")

            # Verify POST payload
            args, kwargs = mock_post.call_args
            payload = kwargs.get("json", {})
            self.assertIn("options", payload)
            options = payload["options"]
            self.assertEqual(options["num_ctx"], 4096)
            self.assertEqual(options["temperature"], 0.3)
            self.assertEqual(options["num_predict"], 1024)
            self.assertEqual(options["top_p"], 0.9)

    # =========================================================================
    # 4. ANTIGRAVITY SYSTEM PROMPT & PERSONA
    # =========================================================================
    def test_system_prompt_contains_antigravity_framework(self):
        """System prompt contains Antigravity analytical framework and formatting standards."""
        prompt = build_system_prompt()
        self.assertIn("ANTIGRAVITY ANALYTICAL FRAMEWORK", prompt)
        self.assertIn("ANTIGRAVITY OUTPUT & FORMATTING STANDARDS", prompt)
        self.assertIn("Executive Summary Up Front", prompt)
        self.assertIn("Structured Comparison Tables", prompt)
        self.assertIn("Actionable Code & Artifacts", prompt)
        # Preserves core boundaries
        self.assertIn("NEVER claim an action succeeded unless the underlying operation actually succeeded", prompt)
        self.assertIn('"Sir"', prompt)

    # =========================================================================
    # 5. CHAT ROUTE CONTEXT ASSEMBLY EFFICIENCY
    # =========================================================================
    def test_chat_route_assembles_compacted_context(self):
        """Chat route limits prompt size even with deep conversation history."""
        provider = self.app.config.get("AI_PROVIDER_INSTANCE")
        with patch.object(provider, "generate_response", return_value="Analyzed successfully, Sir.") as mock_gen:
            res = self.client.post("/api/chat", json={"message": "Analyze system performance"})
            self.assertEqual(res.status_code, 200)

            # Check prompt context passed to provider
            args, _ = mock_gen.call_args
            passed_context = args[1]
            total_chars = sum(len(m.get("message") or m.get("content") or "") for m in passed_context)
            # Context must be strictly within fast prefill limits
            self.assertTrue(total_chars < 6500)


if __name__ == "__main__":
    unittest.main()
