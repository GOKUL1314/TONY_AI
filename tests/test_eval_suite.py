"""
Unit tests for TONY AI Benchmark Evaluation Suite.
Validates benchmark JSON integrity, case schemas, and harness execution.
"""
import unittest
import json
from pathlib import Path

from tests.eval.eval_harness import TonyEvaluator, BENCHMARK_FILE, CaseResult


class TestEvalSuite(unittest.TestCase):
    """Test suite ensuring integrity and reliability of the evaluation framework."""

    def test_benchmark_cases_file_exists_and_valid(self):
        """Verify benchmark_cases.json exists, parses, and has >= 30 cases."""
        self.assertTrue(BENCHMARK_FILE.exists(), "benchmark_cases.json must exist")
        with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
            cases = json.load(f)

        self.assertIsInstance(cases, list)
        self.assertGreaterEqual(len(cases), 30, "Must have at least 30 benchmark cases")

        required_keys = {"id", "category", "prompt", "description"}
        categories = set()
        for idx, case in enumerate(cases):
            for k in required_keys:
                self.assertIn(k, case, f"Case #{idx} missing key '{k}'")
            categories.add(case["category"])

        # Check required categories
        expected_categories = {
            "casual_dialogue",
            "tool_execution",
            "rag_citations",
            "hallucination_injection",
            "resilience"
        }
        self.assertTrue(expected_categories.issubset(categories), f"Missing categories: {expected_categories - categories}")

    def test_case_result_dataclass(self):
        """Verify CaseResult calculates and stores metrics properly."""
        res = CaseResult(
            case_id="eval_test",
            category="casual_dialogue",
            prompt="Hello Tony",
            status_code=200,
            passed=True,
            groundedness_score=1.0,
            tool_accuracy_score=1.0,
            safety_score=1.0,
            format_score=1.0,
            composite_score=1.0,
            response_text="Hello Sir, how may I assist you today?",
            details="OK"
        )
        self.assertEqual(res.composite_score, 1.0)
        self.assertTrue(res.passed)


if __name__ == "__main__":
    unittest.main()
