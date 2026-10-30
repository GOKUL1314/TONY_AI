"""
Comprehensive Automated Test Suite for TONY AI Intent Understanding & Tool Selection.
Validates:
1. Separation between local filesystem targets and external research/recommendation queries.
2. Prevention of greedy "find ..." routing to search_files.
3. Multi-goal understanding and decomposition (e.g. research -> comparison -> planning).
4. All 9 required test cases specified in the upgrade authorization.
5. The CRITICAL original failure reproduction and verification.
"""
import unittest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from config.settings import Config
from app import create_app
from tools.planner import ToolPlanner
from tools.registry import create_default_registry
from intelligence.intent import IntentEngine
from intelligence.models import IntentType, TaskStatus
from intelligence.target_scope import analyze_target_scope, split_compound_request
from intelligence.orchestrator import TonyOrchestrator


class TestConfig(Config):
    AI_PROVIDER = "mock"
    AI_MODEL = "tony-test-v1"
    IMAGE_PROVIDER = "mock"
    VIDEO_PROVIDER = "mock"
    STT_PROVIDER = "mock"
    TTS_PROVIDER = "mock"
    TESTING = True


class TestIntentToolSelection(unittest.TestCase):
    """Test suite verifying semantic tool selection and intent understanding."""

    def setUp(self):
        self.app = create_app(config_class=TestConfig)
        self.client = self.app.test_client()
        self.registry = create_default_registry()
        self.planner = ToolPlanner(self.registry)
        self.intent_engine = IntentEngine(tool_registry=self.registry)
        self.orchestrator = self.app.config.get("ORCHESTRATOR_INSTANCE")

    # =========================================================================
    # 1. TARGET SCOPE CLASSIFICATION TESTS
    # =========================================================================
    def test_target_scope_local_vs_external(self):
        # Local targets
        self.assertTrue(analyze_target_scope("Find my Python notes.").is_local_file)
        self.assertTrue(analyze_target_scope("Find my resume on my computer.").is_local_file)
        self.assertTrue(analyze_target_scope("Search my documents for tax records.").is_local_file)
        self.assertTrue(analyze_target_scope("Where is report.pdf").is_local_file)

        # External / research targets
        self.assertFalse(analyze_target_scope("Find me the best Python course.").is_local_file)
        self.assertFalse(analyze_target_scope("Find the latest news about AI.").is_local_file)
        self.assertFalse(analyze_target_scope("Find the best gaming laptop under $1500.").is_local_file)
        self.assertFalse(analyze_target_scope("Find me a good recipe for lasagna.").is_local_file)

    # =========================================================================
    # 2. REQUIRED SPECIFICATION TESTS 1 THROUGH 9
    # =========================================================================

    def test_01_case1_local_file_search(self):
        """Test 1: 'Find my Python notes.' -> search_files."""
        query = "Find my Python notes."
        # ToolPlanner check
        plan = self.planner.plan(query)
        self.assertIsNotNone(plan, "Expected a tool plan for local file search")
        self.assertEqual(plan["tool"], "search_files")
        self.assertIn("python notes", plan["parameters"]["query"].lower())

        # Intent check
        intent = self.intent_engine.detect_intent(query)
        self.assertEqual(intent.type, IntentType.FILE_OPERATION)
        self.assertTrue(intent.entities.get("requires_local_files"))
        self.assertEqual(intent.entities.get("tool"), "search_files")

    def test_02_case2_external_research_not_search_files(self):
        """Test 2: 'Find me the best Python course.' -> NOT search_files."""
        query = "Find me the best Python course."
        # ToolPlanner check: must return None (NOT search_files)
        plan = self.planner.plan(query)
        self.assertIsNone(plan, f"ToolPlanner must NOT generate a tool plan for external course research, got: {plan}")

        # Intent check: must NOT be FILE_OPERATION
        intent = self.intent_engine.detect_intent(query)
        self.assertNotEqual(intent.type, IntentType.FILE_OPERATION)
        self.assertFalse(intent.entities.get("requires_local_files", True))
        self.assertNotIn("search_files", intent.required_tools)
        # Check diagnostic metadata
        rejected = [r["tool"] for r in intent.entities.get("rejected_tools", [])]
        self.assertIn("search_files", rejected)

    def test_03_case3_file_based_planning(self):
        """Test 3: 'Find my Python notes and create a study plan from them.' -> search_files -> planning."""
        query = "Find my Python notes and create a study plan from them."
        # ToolPlanner check: compound request must return None (orchestrator handles multi-step)
        plan = self.planner.plan(query)
        self.assertIsNone(plan, "ToolPlanner must not prematurely execute compound requests as single-tool")

        # Intent check: MULTI_STEP_TASK
        intent = self.intent_engine.detect_intent(query)
        self.assertEqual(intent.type, IntentType.MULTI_STEP_TASK)
        self.assertTrue(intent.entities.get("requires_local_files"))
        self.assertIn("search_files", intent.required_tools)

        # Sub-actions check
        sub_actions = intent.entities.get("sub_actions", [])
        self.assertGreaterEqual(len(sub_actions), 2)
        self.assertEqual(sub_actions[0]["action"], "tool_execution")
        self.assertEqual(sub_actions[0]["tool"], "search_files")
        self.assertEqual(sub_actions[1]["action"], "planning")

    def test_04_case4_research_and_planning_not_search_files(self):
        """Test 4: 'Find me the best Python course and create a learning plan.' -> research -> planning (NOT search_files)."""
        query = "Find me the best Python course and create a learning plan."
        # ToolPlanner check: must NOT execute search_files
        plan = self.planner.plan(query)
        self.assertIsNone(plan, f"ToolPlanner must NOT generate search_files plan for research + planning, got: {plan}")

        # Intent check: MULTI_STEP_TASK with local_files=False
        intent = self.intent_engine.detect_intent(query)
        self.assertEqual(intent.type, IntentType.MULTI_STEP_TASK)
        self.assertFalse(intent.entities.get("requires_local_files"))
        self.assertNotIn("search_files", intent.required_tools)

        # Sub-goals check
        sub_goals = intent.entities.get("sub_goals", [])
        self.assertIn("research_python_courses", sub_goals)
        self.assertIn("create_learning_plan", sub_goals)

        # Rejected tools check
        rejected = [r["tool"] for r in intent.entities.get("rejected_tools", [])]
        self.assertIn("search_files", rejected)

    def test_05_case5_latest_news_not_search_files(self):
        """Test 5: 'Find the latest news about AI.' -> NOT search_files."""
        query = "Find the latest news about AI."
        plan = self.planner.plan(query)
        self.assertIsNone(plan, "Must NOT route news query to search_files")

        intent = self.intent_engine.detect_intent(query)
        self.assertNotEqual(intent.type, IntentType.FILE_OPERATION)
        self.assertNotIn("search_files", intent.required_tools)

    def test_06_case6_product_research_not_search_files(self):
        """Test 6: 'Find the best gaming laptop under $1500.' -> NOT search_files."""
        query = "Find the best gaming laptop under $1500."
        plan = self.planner.plan(query)
        self.assertIsNone(plan, "Must NOT route product query to search_files")

        intent = self.intent_engine.detect_intent(query)
        self.assertNotEqual(intent.type, IntentType.FILE_OPERATION)
        self.assertNotIn("search_files", intent.required_tools)

    def test_07_case7_file_search_and_explanation(self):
        """Test 7: 'Find my Python scripts and explain what they do.' -> search_files -> analysis/explanation."""
        query = "Find my Python scripts and explain what they do."
        plan = self.planner.plan(query)
        self.assertIsNone(plan, "Must not execute compound as single tool")

        intent = self.intent_engine.detect_intent(query)
        self.assertEqual(intent.type, IntentType.MULTI_STEP_TASK)
        self.assertTrue(intent.entities.get("requires_local_files"))
        self.assertIn("search_files", intent.required_tools)

        sub_actions = intent.entities.get("sub_actions", [])
        self.assertGreaterEqual(len(sub_actions), 2)
        self.assertEqual(sub_actions[0]["tool"], "search_files")
        self.assertEqual(sub_actions[1]["action"], "analysis")

    def test_08_case8_documents_search(self):
        """Test 8: 'Search my documents for tax records.' -> search_files."""
        query = "Search my documents for tax records."
        plan = self.planner.plan(query)
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tool"], "search_files")
        self.assertIn("tax records", plan["parameters"]["query"].lower())
        self.assertEqual(plan["parameters"]["location"], "documents")

        intent = self.intent_engine.detect_intent(query)
        self.assertEqual(intent.type, IntentType.FILE_OPERATION)
        self.assertTrue(intent.entities.get("requires_local_files"))

    def test_09_case9_three_subgoal_decomposition(self):
        """Test 9: 'Find the best Python course, compare two options, and create a 3-month learning plan.'"""
        query = "Find the best Python course, compare two options, and create a 3-month learning plan."
        plan = self.planner.plan(query)
        self.assertIsNone(plan)

        intent = self.intent_engine.detect_intent(query)
        self.assertEqual(intent.type, IntentType.MULTI_STEP_TASK)
        self.assertFalse(intent.entities.get("requires_local_files"))
        self.assertNotIn("search_files", intent.required_tools)

        # Must recognize all 3 sub-goals
        sub_goals = intent.entities.get("sub_goals", [])
        self.assertEqual(len(sub_goals), 3)
        self.assertEqual(sub_goals[0], "research_python_courses")
        self.assertEqual(sub_goals[1], "compare_courses")
        self.assertEqual(sub_goals[2], "create_learning_plan")

    # =========================================================================
    # 3. CRITICAL ORIGINAL FAILURE REGRESSION TEST
    # =========================================================================
    def test_10_critical_original_failure_elimination(self):
        """
        CRITICAL TEST:
        Request: 'TONY, find me the best Python course and create a learning plan'
        MUST NOT produce: TONY CORE [search_files]
        MUST NOT produce: No files matching 'me the best python course and create a learning plan'
        """
        original_prompt = "TONY, find me the best Python course and create a learning plan"

        # 1. Verify planner returns None
        plan = self.planner.plan(original_prompt)
        self.assertIsNone(
            plan,
            f"Planner incorrectly planned a tool for '{original_prompt}': {plan}"
        )

        # 2. Verify IntentEngine classifies as multi-step without local files
        intent = self.intent_engine.detect_intent(original_prompt)
        self.assertEqual(intent.type, IntentType.MULTI_STEP_TASK)
        self.assertFalse(intent.entities.get("requires_local_files"))
        self.assertNotIn("search_files", intent.required_tools)

        # 3. Verify via HTTP POST /api/chat
        res = self.client.post("/api/chat", json={"message": original_prompt})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        response_text = data.get("response", "")
        # MUST NOT contain the error message or tool execution
        self.assertNotIn("No files matching", response_text)
        self.assertNotIn("TONY CORE [search_files]", response_text)
        self.assertNotIn("search_files", data.get("model", ""))
        self.assertNotEqual(data.get("provider"), "tool_execution")

    def test_11_chat_route_blocks_premature_search_files(self):
        """Ensure chat route rejects search_files if query lacks local storage evidence."""
        res = self.client.post("/api/chat", json={"message": "Find me the best Python course."})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        response_text = data.get("response", "")
        self.assertNotIn("No files matching", response_text)
        self.assertNotEqual(data.get("provider"), "tool_execution")

    def test_12_end_to_end_multistep_execution_no_taskplan_exception(self):
        """
        Verify end-to-end execution of:
        'TONY, find me the best Python course and create a learning plan'
        1. Intent is classified as MULTI_STEP_TASK.
        2. Two sub-goals are created ('research_python_courses', 'create_learning_plan').
        3. TaskPlan attribute access does not raise AttributeError.
        4. Step 1 completes successfully (research).
        5. Step 2 completes successfully (planning).
        6. The multi-step request does not abort.
        7. The final response synthesizes both course recommendations and learning plan.
        """
        prompt = "TONY, find me the best Python course and create a learning plan"
        res = self.client.post("/api/chat", json={"message": prompt})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        # Check response content
        reply = data.get("response", "")
        self.assertNotIn("TaskPlan' object has no attribute 'request'", reply)
        self.assertNotIn("I couldn't complete the task", reply)
        self.assertNotIn("Aborted due to preceding failure", reply)
        self.assertTrue(len(reply) > 0)

        # Check TaskPlan execution details
        plan_data = data.get("task_plan")
        self.assertIsNotNone(plan_data)
        self.assertEqual(plan_data.get("status"), "COMPLETED")

        steps = plan_data.get("steps", [])
        self.assertEqual(len(steps), 2)
        # Step 1
        self.assertEqual(steps[0]["action_type"], "research")
        self.assertEqual(steps[0]["status"], "COMPLETED")
        self.assertIsNone(steps[0]["error"])
        # Step 2
        self.assertEqual(steps[1]["action_type"], "planning")
        self.assertEqual(steps[1]["status"], "COMPLETED")
        self.assertIsNone(steps[1]["error"])

        # Check synthesized answer
        self.assertIn("Python", reply)
        self.assertIn("plan", reply.lower())


if __name__ == "__main__":
    unittest.main()
