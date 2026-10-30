"""
Unit and Integration Tests for TONY AI Stage 5:
Tool Execution & Safe Windows System Automation.

Validates:
- Tool Registry (registration, categories, retrieval, counts)
- Permission Manager (sandboxing, path traversal blocking, protected paths, command injection rejection, risk levels)
- Confirmation Manager (pending action lifecycle, timeouts, natural turn retrieval)
- Tool Planner (natural language utterance parsing to structured tool plans, conversational fallback)
- Tool Executor (safe execution, risk enforcement, critical refusal, confirmation gates, telemetry logging)
- REST API Endpoints (/api/tools, /api/tools/execute, /api/tools/confirm, /api/tools/cancel, /api/tools/pending, /api/tools/stats)
- Chat Integration (/api/chat tool planning, multi-turn voice/chat confirmation, status telemetry)
- Filesystem safety (safe sandbox folder/file creation, copy, rename, delete)
"""
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from app import create_app
from config.settings import Config
from tools.schemas import RiskLevel, ToolParameter, ToolDefinition, ToolExecutionResult, PendingAction
from tools.base import BaseTool
from tools.permissions import PermissionManager
from tools.confirmation import ConfirmationManager
from tools.registry import ToolRegistry, create_default_registry
from tools.planner import ToolPlanner
from tools.executor import ToolExecutor
from tools.system.applications import OpenApplicationTool
from tools.browser.browser import OpenWebsiteTool
from tools.filesystem.folders import CreateFolderTool, DeleteFolderTool
from tools.filesystem.files import CreateFileTool, DeleteFileTool
from tools.utilities.datetime_tool import GetSystemTimeTool


class TestToolRegistry(unittest.TestCase):
    """Test Tool Registry registration, category filtering, and retrieval."""

    def setUp(self):
        self.registry = ToolRegistry()

    def test_register_and_retrieve(self):
        class DummyTool(BaseTool):
            @property
            def definition(self):
                return ToolDefinition(name="dummy", description="Dummy test tool", category="test")
            def execute(self, params):
                return self.success("Dummy executed")

        tool = DummyTool()
        self.registry.register(tool)
        self.assertTrue(self.registry.is_registered("dummy"))
        self.assertEqual(self.registry.get_tool("dummy"), tool)
        self.assertEqual(self.registry.count(), 1)

    def test_category_filtering(self):
        default_reg = create_default_registry()
        self.assertGreaterEqual(default_reg.count(), 20)

        sys_tools = default_reg.get_tools_by_category("system")
        fs_tools = default_reg.get_tools_by_category("filesystem")
        browser_tools = default_reg.get_tools_by_category("browser")
        util_tools = default_reg.get_tools_by_category("utilities")

        self.assertGreaterEqual(len(sys_tools), 5)
        self.assertGreaterEqual(len(fs_tools), 8)
        self.assertGreaterEqual(len(browser_tools), 1)
        self.assertGreaterEqual(len(util_tools), 2)


class TestPermissionManager(unittest.TestCase):
    """Test strict security sandboxing, path traversal blocking, and risk evaluation."""

    def test_path_traversal_rejection(self):
        # Escaping base dir with parent relative paths
        is_safe, err = PermissionManager.validate_safe_path("../../../Windows/System32", "desktop")
        self.assertFalse(is_safe)
        self.assertIn("Path traversal", err)

        is_safe, err = PermissionManager.validate_safe_path("foo/../../bar", "documents")
        self.assertFalse(is_safe)

    def test_protected_system_paths(self):
        is_safe, err = PermissionManager.validate_safe_path("C:\\Windows\\System32\\cmd.exe")
        self.assertFalse(is_safe)
        self.assertIn("Access denied", err)

        is_safe, err = PermissionManager.validate_safe_path("C:\\Program Files\\app.exe")
        self.assertFalse(is_safe)

    def test_dangerous_executable_rejection(self):
        is_safe, err = PermissionManager.validate_executable_path("script.bat")
        self.assertFalse(is_safe)
        self.assertIn("Execution of executable", err)

        is_safe, err = PermissionManager.validate_executable_path("virus.exe")
        self.assertFalse(is_safe)

    def test_command_injection_rejection(self):
        is_safe, err = PermissionManager.validate_command_safety("notepad; rm -rf /")
        self.assertFalse(is_safe)
        self.assertIn("Disallowed shell metacharacter", err)

        is_safe, err = PermissionManager.validate_command_safety("echo hello | clip")
        self.assertFalse(is_safe)

        is_safe, err = PermissionManager.validate_command_safety("notepad")
        self.assertTrue(is_safe)

    def test_url_validation(self):
        norm_url, err = PermissionManager.validate_url("https://www.youtube.com")
        self.assertIsNone(err)
        self.assertEqual(norm_url, "https://www.youtube.com")

        norm_url, err = PermissionManager.validate_url("http://localhost:5000")
        self.assertIsNone(err)
        self.assertEqual(norm_url, "http://localhost:5000")

        norm_url, err = PermissionManager.validate_url("file:///C:/Windows/System32")
        self.assertIsNotNone(err)
        self.assertIsNone(norm_url)

        norm_url, err = PermissionManager.validate_url("javascript:alert(1)")
        self.assertIsNotNone(err)
        self.assertIsNone(norm_url)

    def test_risk_level_evaluation(self):
        # Low risk
        self.assertEqual(
            PermissionManager.evaluate_risk("get_system_time", {}),
            RiskLevel.LOW
        )
        self.assertEqual(
            PermissionManager.evaluate_risk("open_application", {"application": "notepad"}),
            RiskLevel.LOW
        )
        # High risk
        self.assertEqual(
            PermissionManager.evaluate_risk("delete_file", {"name": "test.txt", "location": "desktop"}),
            RiskLevel.HIGH
        )
        self.assertEqual(
            PermissionManager.evaluate_risk("delete_folder", {"name": "Projects", "location": "desktop"}),
            RiskLevel.HIGH
        )
        # Critical risk
        self.assertEqual(
            PermissionManager.evaluate_risk("delete_folder", {"name": "Windows", "location": "C:\\"}),
            RiskLevel.CRITICAL
        )
        self.assertEqual(
            PermissionManager.evaluate_risk("open_website", {"target": "javascript:alert(1)"}),
            RiskLevel.CRITICAL
        )


class TestConfirmationManager(unittest.TestCase):
    """Test pending action lifecycle and timeout management."""

    def setUp(self):
        self.mgr = ConfirmationManager(default_timeout=2)

    def test_create_and_confirm(self):
        pending = self.mgr.create_pending("delete_file", {"name": "notes.txt"}, "Delete notes")
        self.assertTrue(pending.id.startswith("act_"))
        self.assertEqual(self.mgr.get_active_pending(), pending)

        confirmed = self.mgr.confirm(pending.id)
        self.assertEqual(confirmed.id, pending.id)
        # Popped, so active should now be None
        self.assertIsNone(self.mgr.get_active_pending())

    def test_cancel_pending(self):
        pending = self.mgr.create_pending("delete_folder", {"name": "demo"}, "Delete demo folder")
        success = self.mgr.cancel(pending.id)
        self.assertTrue(success)
        self.assertIsNone(self.mgr.get_pending(pending.id))

    def test_expired_pending(self):
        pending = self.mgr.create_pending("delete_file", {}, "Quick test", timeout_seconds=1)
        time.sleep(1.1)
        self.assertTrue(pending.is_expired())
        self.assertIsNone(self.mgr.get_pending(pending.id))
        self.assertIsNone(self.mgr.get_active_pending())


class TestToolPlanner(unittest.TestCase):
    """Test natural language command classification into structured tool plans."""

    def setUp(self):
        self.registry = create_default_registry()
        self.planner = ToolPlanner(self.registry)

    def test_time_queries(self):
        for q in ["what time is it?", "Tony, what is the time?", "tell me the time", "what date is it today"]:
            plan = self.planner.plan(q)
            self.assertIsNotNone(plan, f"Failed on: {q}")
            self.assertEqual(plan["tool"], "get_system_time")

    def test_volume_commands(self):
        plan = self.planner.plan("Tony, volume up")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tool"], "volume_up")

        plan = self.planner.plan("decrease volume by 4")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tool"], "volume_down")
        self.assertEqual(plan["parameters"]["steps"], 4)

        plan = self.planner.plan("mute audio")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tool"], "volume_mute")

    def test_media_commands(self):
        plan = self.planner.plan("pause music")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tool"], "play_pause")

        plan = self.planner.plan("Tony, next track")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tool"], "next_track")

    def test_website_launcher(self):
        plan = self.planner.plan("Tony, open YouTube")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tool"], "open_website")
        self.assertEqual(plan["parameters"]["target"].lower(), "youtube")

        plan = self.planner.plan("open github.com")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tool"], "open_website")

    def test_application_launcher(self):
        plan = self.planner.plan("Tony, open Notepad")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tool"], "open_application")
        self.assertEqual(plan["parameters"]["application"], "notepad")

        plan = self.planner.plan("launch calculator")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tool"], "open_application")
        self.assertEqual(plan["parameters"]["application"], "calculator")

    def test_folder_file_commands(self):
        plan = self.planner.plan("Tony, create a folder called Projects on my Desktop")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tool"], "create_folder")
        self.assertEqual(plan["parameters"]["name"], "Projects")
        self.assertEqual(plan["parameters"]["location"].lower(), "desktop")

        plan = self.planner.plan("delete file report.txt")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tool"], "delete_file")
        self.assertIn("report.txt", plan["parameters"]["target"])

    def test_conversational_queries_return_none(self):
        conversational = [
            "who are you?",
            "what can you do?",
            "tell me a joke about robots",
            "explain quantum physics",
            "hello Tony",
            "I feel tired today",
            "what is my name?"
        ]
        for c in conversational:
            self.assertIsNone(self.planner.plan(c), f"Expected None for conversational: {c}")


class TestToolExecutor(unittest.TestCase):
    """Test Tool Executor risk gating, confirmation requirements, and critical refusals."""

    def setUp(self):
        self.registry = create_default_registry()
        self.confirm_mgr = ConfirmationManager(default_timeout=30)
        self.executor = ToolExecutor(self.registry, self.confirm_mgr)

    def test_execute_safe_tool(self):
        result = self.executor.execute_plan({"tool": "get_system_time", "parameters": {}})
        self.assertTrue(result.success)
        self.assertIn("It is currently", result.message)
        self.assertEqual(result.risk_level, "low")
        self.assertFalse(result.requires_confirmation)

    def test_high_risk_requires_confirmation(self):
        result = self.executor.execute_plan({
            "tool": "delete_folder",
            "parameters": {"name": "TestDir", "location": "desktop"}
        })
        self.assertFalse(result.success)
        self.assertTrue(result.requires_confirmation)
        self.assertIsNotNone(result.confirmation_id)
        self.assertEqual(result.risk_level, "high")

    def test_critical_operation_refusal(self):
        result = self.executor.execute_plan({
            "tool": "delete_folder",
            "parameters": {"name": "Windows", "location": "C:\\"}
        })
        self.assertFalse(result.success)
        self.assertFalse(result.requires_confirmation)
        self.assertEqual(result.error_code, "CRITICAL_OPERATION_BLOCKED")

    def test_confirmation_lifecycle(self):
        # 1. Trigger action requiring confirmation
        res1 = self.executor.execute_plan({
            "tool": "delete_file",
            "parameters": {"name": "sample.txt", "location": "desktop"}
        })
        self.assertTrue(res1.requires_confirmation)
        action_id = res1.confirmation_id

        # 2. Mock underlying tool execution and confirm
        with patch.object(DeleteFileTool, "execute", return_value=ToolExecutionResult(success=True, tool="delete_file", message="File deleted successfully.")):
            confirmed_res = self.executor.confirm_action(action_id)
            self.assertTrue(confirmed_res.success)
            self.assertIn("deleted successfully", confirmed_res.message)


class TestToolsFilesystemCRUD(unittest.TestCase):
    """Test sandboxed filesystem tools in an isolated temp test directory."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        def mock_resolve_safe_path(target_str, default_location="Desktop"):
            name = Path(target_str).name
            return self.temp_path / name, None

        self.patcher = patch.object(PermissionManager, "resolve_safe_path", side_effect=mock_resolve_safe_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_folder_lifecycle(self):
        create_tool = CreateFolderTool()
        del_tool = DeleteFolderTool()

        # 1. Create folder
        res = create_tool.execute({"name": "TestFolder", "location": "desktop"})
        self.assertTrue(res.success)
        folder_path = self.temp_path / "TestFolder"
        self.assertTrue(folder_path.is_dir())

        # 2. Delete folder
        del_res = del_tool.execute({"name": "TestFolder", "location": "desktop"})
        self.assertTrue(del_res.success)
        self.assertFalse(folder_path.exists())

    def test_file_lifecycle(self):
        create_tool = CreateFileTool()
        del_tool = DeleteFileTool()

        # 1. Create file with content
        res = create_tool.execute({"name": "test.txt", "location": "documents", "content": "Hello TONY Stage 5"})
        self.assertTrue(res.success)
        file_path = self.temp_path / "test.txt"
        self.assertTrue(file_path.is_file())
        self.assertEqual(file_path.read_text(encoding="utf-8"), "Hello TONY Stage 5")

        # 2. Delete file
        del_res = del_tool.execute({"name": "test.txt", "location": "documents"})
        self.assertTrue(del_res.success)
        self.assertFalse(file_path.exists())


class TestToolsAPIEndpoints(unittest.TestCase):
    """Test REST API endpoints for Tools subsystem."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_api_tools.db")

        class CustomConfig(Config):
            TESTING = True
            DEBUG = False
            AI_PROVIDER = "mock"
            STT_PROVIDER = "mock"
            TTS_PROVIDER = "mock"
            MEMORY_DATABASE = self.db_path
            MEMORY_ENABLED = True
            MEMORY_AUTO_SAVE = True
            TOOLS_ENABLED = True
            TOOL_CONFIRMATION_ENABLED = True
            TOOL_CONFIRMATION_TIMEOUT = 10

        self.app = create_app(CustomConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_list_tools(self):
        res = self.client.get("/api/tools")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(data["count"], 20)

    def test_list_tools_by_category(self):
        res = self.client.get("/api/tools?category=filesystem")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        for tool in data["tools"]:
            self.assertEqual(tool["category"], "filesystem")

    def test_get_specific_tool(self):
        res = self.client.get("/api/tools/get_system_time")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["tool"]["name"], "get_system_time")

    def test_get_nonexistent_tool(self):
        res = self.client.get("/api/tools/imaginary_tool_404")
        self.assertEqual(res.status_code, 404)

    def test_execute_safe_tool(self):
        res = self.client.post("/api/tools/execute", json={
            "tool": "get_system_time",
            "parameters": {}
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("current", data["message"].lower())

    def test_execute_destructive_requires_confirmation(self):
        res = self.client.post("/api/tools/execute", json={
            "tool": "delete_file",
            "parameters": {"name": "sample.txt", "location": "desktop"}
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertTrue(data["requires_confirmation"])
        self.assertIsNotNone(data["confirmation_id"])

        # Check pending actions endpoint
        pending_res = self.client.get("/api/tools/pending")
        self.assertEqual(pending_res.status_code, 200)
        pending_data = pending_res.get_json()
        self.assertGreaterEqual(pending_data["count"], 1)

        # Cancel action
        cancel_res = self.client.post("/api/tools/cancel", json={
            "confirmation_id": data["confirmation_id"]
        })
        self.assertEqual(cancel_res.status_code, 200)

    def test_tool_stats(self):
        res = self.client.get("/api/tools/stats")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("total_tools", data["stats"])
        self.assertIn("active_pending_confirmations", data["stats"])


class TestChatToolIntegration(unittest.TestCase):
    """Test full chat pipeline integration with tool planning and natural language confirmations."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_chat_tools.db")

        class CustomConfig(Config):
            TESTING = True
            DEBUG = False
            AI_PROVIDER = "mock"
            STT_PROVIDER = "mock"
            TTS_PROVIDER = "mock"
            MEMORY_DATABASE = self.db_path
            MEMORY_ENABLED = True
            MEMORY_AUTO_SAVE = True
            TOOLS_ENABLED = True
            TOOL_CONFIRMATION_ENABLED = True
            TOOL_CONFIRMATION_TIMEOUT = 10

        self.app = create_app(CustomConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_chat_tool_planning_execution(self):
        res = self.client.post("/api/chat", json={"message": "Tony, what time is it?"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["provider"], "tool_execution")
        self.assertEqual(data["model"], "get_system_time")
        self.assertIn("current", data["response"].lower())

    def test_chat_tool_confirmation_workflow(self):
        # 1. Ask TONY to delete something (high risk)
        res1 = self.client.post("/api/chat", json={"message": "Tony, delete folder Temp on my Desktop"})
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        self.assertIn("Confirmation Required", data1["response"])

        # 2. Natural language confirmation "Tony, yes"
        with patch.object(DeleteFolderTool, "execute", return_value=ToolExecutionResult(success=True, tool="delete_folder", message="Folder deleted")):
            res2 = self.client.post("/api/chat", json={"message": "Yes, Tony"})
            self.assertEqual(res2.status_code, 200)
            data2 = res2.get_json()
            self.assertEqual(data2["provider"], "tool_confirmation")
            self.assertIn("Confirmed", data2["response"])

    def test_chat_tool_cancel_workflow(self):
        # 1. Ask TONY to delete
        self.client.post("/api/chat", json={"message": "delete folder OldData on my Desktop"})
        # 2. Cancel with "Tony, cancel"
        res = self.client.post("/api/chat", json={"message": "Cancel"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["provider"], "tool_confirmation")
        self.assertIn("Action cancelled", data["response"])

    def test_delete_file_chat_never_deletes_without_confirmation(self):
        """Prove that destructive file deletion in /api/chat cannot run without explicit confirmation."""
        sandbox_dir = tempfile.mkdtemp()
        test_file = Path(sandbox_dir) / "eval_note.txt"
        test_file.write_text("Sensitive user content", encoding="utf-8")
        self.assertTrue(test_file.exists(), "Pre-condition: test file must exist")

        def mock_resolve(target_str, default_location="Desktop"):
            return test_file, None

        with patch.object(PermissionManager, "resolve_safe_path", side_effect=mock_resolve):
            # 1. Dispatch delete request via chat
            res1 = self.client.post("/api/chat", json={"message": "Delete the file eval_note.txt from my Desktop"})
            self.assertEqual(res1.status_code, 200)
            data1 = res1.get_json()

            # Prove confirmation was required and registered
            self.assertTrue(data1.get("requires_confirmation"), "Must require confirmation")
            self.assertIn("confirmation required", data1.get("response", "").lower())
            self.assertEqual(data1.get("model"), "delete_file")

            conf_mgr = self.app.config.get("TOOL_CONFIRMATION_INSTANCE")
            pending = conf_mgr.get_active_pending()
            self.assertIsNotNone(pending, "Active pending action must be created in ConfirmationManager")
            self.assertEqual(pending.tool_name, "delete_file")

            # CRITICAL SAFETY INVARIANT: File MUST NOT have been deleted!
            self.assertTrue(test_file.exists(), "Destructive tool MUST NOT execute before confirmation!")

            # 2. Confirm via chat turn
            res2 = self.client.post("/api/chat", json={"message": "Yes, confirm"})
            self.assertEqual(res2.status_code, 200)
            data2 = res2.get_json()
            self.assertEqual(data2.get("provider"), "tool_confirmation")
            self.assertIn("confirmed", data2.get("response", "").lower())

            # Only now should the file be deleted
            self.assertFalse(test_file.exists(), "File should be deleted only after confirmation")

        shutil.rmtree(sandbox_dir, ignore_errors=True)

    def test_delete_folder_chat_never_deletes_without_confirmation(self):
        """Prove that destructive folder deletion in /api/chat cannot run without explicit confirmation."""
        sandbox_dir = tempfile.mkdtemp()
        test_folder = Path(sandbox_dir) / "TonyEvalTest"
        test_folder.mkdir(parents=True, exist_ok=True)
        (test_folder / "file.txt").write_text("data", encoding="utf-8")
        self.assertTrue(test_folder.exists(), "Pre-condition: test folder must exist")

        def mock_resolve(target_str, default_location="Desktop"):
            return test_folder, None

        with patch.object(PermissionManager, "resolve_safe_path", side_effect=mock_resolve):
            # 1. Dispatch folder deletion request via chat
            res1 = self.client.post("/api/chat", json={"message": "Delete the folder called TonyEvalTest on Desktop"})
            self.assertEqual(res1.status_code, 200)
            data1 = res1.get_json()

            self.assertTrue(data1.get("requires_confirmation"), "Must require confirmation")
            self.assertIn("confirmation required", data1.get("response", "").lower())
            self.assertEqual(data1.get("model"), "delete_folder")

            conf_mgr = self.app.config.get("TOOL_CONFIRMATION_INSTANCE")
            pending = conf_mgr.get_active_pending()
            self.assertIsNotNone(pending, "Active pending action must be created in ConfirmationManager")
            self.assertEqual(pending.tool_name, "delete_folder")

            # CRITICAL SAFETY INVARIANT: Folder MUST NOT have been deleted!
            self.assertTrue(test_folder.exists(), "Folder MUST NOT be deleted before confirmation!")

            # 2. Cancel via chat turn
            res2 = self.client.post("/api/chat", json={"message": "No, cancel it"})
            self.assertEqual(res2.status_code, 200)
            data2 = res2.get_json()
            self.assertEqual(data2.get("provider"), "tool_confirmation")
            self.assertIn("cancelled", data2.get("response", "").lower())

            # Folder MUST STILL exist because action was cancelled
            self.assertTrue(test_folder.exists(), "Folder must remain intact after cancellation")

        shutil.rmtree(sandbox_dir, ignore_errors=True)

    def test_all_destructive_deletion_phrasings_require_confirmation(self):
        """Prove that multiple phrasings of file and folder deletions all go through ConfirmationManager."""
        conf_mgr = self.app.config.get("TOOL_CONFIRMATION_INSTANCE")

        phrasings = [
            ("Delete the file eval_note.txt from my Desktop", "delete_file"),
            ("Delete the folder called TonyEvalTest on Desktop", "delete_folder"),
            ("Remove the file eval_note.txt from Desktop", "delete_file"),
            ("Delete folder called TonyEvalTest on Desktop", "delete_folder"),
            ("delete directory called TonyEvalTest", "delete_folder"),
            ("delete file 'test.txt' on Desktop", "delete_file"),
            ("remove folder Temp on my Desktop", "delete_folder"),
        ]

        for phrase, expected_tool in phrasings:
            conf_mgr.cancel_all()
            res = self.client.post("/api/chat", json={"message": phrase})
            self.assertEqual(res.status_code, 200, f"Failed for phrase: {phrase}")
            data = res.get_json()

            self.assertTrue(
                data.get("requires_confirmation"),
                f"Phrase '{phrase}' bypassed confirmation! Response: {data.get('response')}"
            )
            self.assertEqual(data.get("model"), expected_tool, f"Expected {expected_tool} for '{phrase}'")

            pending = conf_mgr.get_active_pending()
            self.assertIsNotNone(pending, f"No pending action in ConfirmationManager for phrase: '{phrase}'")
            self.assertEqual(pending.tool_name, expected_tool)

    def test_destructive_direct_tool_execute_requires_confirmation(self):
        """Prove that direct /api/tools/execute cannot execute destructive tools without confirmation."""
        # delete_file direct call
        res_file = self.client.post("/api/tools/execute", json={"tool": "delete_file", "parameters": {"target": "notes.txt"}})
        self.assertEqual(res_file.status_code, 200)
        data_file = res_file.get_json()
        self.assertTrue(data_file.get("requires_confirmation"))
        self.assertFalse(data_file.get("success"))
        self.assertIsNotNone(data_file.get("confirmation_id"))

        # delete_folder direct call
        res_fol = self.client.post("/api/tools/execute", json={"tool": "delete_folder", "parameters": {"target": "OldFolder"}})
        self.assertEqual(res_fol.status_code, 200)
        data_fol = res_fol.get_json()
        self.assertTrue(data_fol.get("requires_confirmation"))
        self.assertFalse(data_fol.get("success"))
        self.assertIsNotNone(data_fol.get("confirmation_id"))

    def test_chat_status_endpoint(self):
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["stage"], 5)
        self.assertIn("tools", data)
        self.assertGreaterEqual(data["tools"]["total_tools"], 20)


if __name__ == "__main__":
    unittest.main()
