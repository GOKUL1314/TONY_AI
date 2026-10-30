"""
Automated Test Suite for TONY AI Controlled Self-Upgrade Subsystem.
Validates diagnostic, upgrade planning, AST syntax validation, backup checkpointing,
patch application, test verification, automatic rollbacks, retry limits, and security restrictions.
"""
import unittest
from unittest.mock import MagicMock, patch
import tempfile
import shutil
from pathlib import Path

from config.settings import Config
from app import create_app
from self_upgrade import (
    SelfUpgradeManager,
    UpgradeSecurityPolicy,
    SecurityViolationError,
    ProtectedFileError,
    RiskLevel,
    UpgradeStatus,
    PatchValidationError
)
from self_upgrade.validator import PatchValidator
from self_upgrade.tester import UpgradeTestRunner


class TestSelfUpgradeSubsystem(unittest.TestCase):
    """Test suite for Self-Upgrade Subsystem."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)
        self.app = create_app()
        self.client = self.app.test_client()

        # Create simulated project structure in temp dir
        self.proj_dir = self.test_path / "project"
        self.proj_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = self.test_path / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Create mock target files
        (self.proj_dir / "target.py").write_text("# Target file\ndef greet():\n    return 'Hello'\n", encoding="utf-8")
        (self.proj_dir / ".env").write_text("SECRET_KEY=confidential_key\n", encoding="utf-8")

        self.mgr = SelfUpgradeManager(
            project_root=self.proj_dir,
            data_dir=self.data_dir,
            app_context=self.app
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # 1. Diagnostic & Inspection Tests
    def test_diagnostic_report_structure(self):
        report = self.mgr.diagnose()
        self.assertIsNotNone(report.timestamp)
        self.assertIn("intelligence", report.subsystems)
        self.assertIn("ai_provider", report.subsystems)
        self.assertIn("tools", report.subsystems)
        self.assertIsInstance(report.recommendations, list)

    # 2. Upgrade Planning Tests
    def test_upgrade_planning_valid_files(self):
        plan = self.mgr.create_plan(
            reason="Enhance greeting function",
            files_to_modify=["target.py"],
            proposed_changes={"target.py": "def greet():\n    return 'Hello Sir'\n"}
        )
        self.assertEqual(plan.status, UpgradeStatus.PLANNED)
        self.assertEqual(plan.risk_level, RiskLevel.LOW)
        self.assertTrue(plan.requires_confirmation)
        self.assertEqual(len(plan.steps), 1)

    # 3. Security Policy Enforcement
    def test_security_blocks_protected_files(self):
        # Must block .env
        with self.assertRaises(ProtectedFileError):
            UpgradeSecurityPolicy.validate_target_path(".env", self.proj_dir)

        # Must block .git
        with self.assertRaises(ProtectedFileError):
            UpgradeSecurityPolicy.validate_target_path(".git/config", self.proj_dir)

        # Must block venv
        with self.assertRaises(ProtectedFileError):
            UpgradeSecurityPolicy.validate_target_path("venv/Scripts/python.exe", self.proj_dir)

        # Must block database files
        with self.assertRaises(ProtectedFileError):
            UpgradeSecurityPolicy.validate_target_path("data/memory.db", self.proj_dir)

    def test_security_blocks_arbitrary_shell_and_cmd(self):
        malicious_code = "import os\nos.system('powershell -Command Remove-Item -Recurse C:/')\n"
        with self.assertRaises(SecurityViolationError):
            UpgradeSecurityPolicy.validate_code_safety(malicious_code, "dangerous.py")

    def test_security_blocks_test_tampering(self):
        tampered_test = "def test_feature(self):\n    pass\n"
        with self.assertRaises(SecurityViolationError):
            UpgradeSecurityPolicy.validate_code_safety(tampered_test, "test_feature.py")

    def test_patch_validator_syntax_checking(self):
        bad_syntax = "def broken_func(:\n    return 42"
        with self.assertRaises(PatchValidationError):
            PatchValidator.validate_content(bad_syntax, "broken.py")

    # 4. Checkpoint Backup and Rollback Tests
    def test_backup_and_rollback_flow(self):
        target = self.proj_dir / "target.py"
        original_content = target.read_text(encoding="utf-8")

        plan = self.mgr.create_plan(
            reason="Test backup",
            files_to_modify=["target.py"],
            proposed_changes={"target.py": "# Modified content\n"}
        )

        backup_rec = self.mgr.backup_mgr.create_backup(plan)
        self.assertTrue(Path(backup_rec.backup_dir).exists())

        # Modify file
        target.write_text("# Modified content\n", encoding="utf-8")
        self.assertNotEqual(target.read_text(encoding="utf-8"), original_content)

        # Rollback
        self.mgr.rollback(plan.upgrade_id)
        self.assertEqual(target.read_text(encoding="utf-8"), original_content)

    # 5. Failed Upgrade and Auto-Rollback on Test Failure
    def test_failed_upgrade_automatically_rolls_back(self):
        target = self.proj_dir / "target.py"
        orig_text = target.read_text(encoding="utf-8")

        plan = self.mgr.create_plan(
            reason="Failing change",
            files_to_modify=["target.py"],
            proposed_changes={"target.py": "def greet():\n    return 'Broken'\n"}
        )

        # Mock tester to return failed test result
        with patch.object(self.mgr.tester, "run_tests") as mock_run:
            from self_upgrade.models import TestRunResult
            mock_run.return_value = TestRunResult(
                total=10, passed=8, failed=2, errors=0, success=False, output_summary="FAIL"
            )

            res = self.mgr.apply_upgrade(plan.upgrade_id)
            self.assertFalse(res["success"])
            self.assertIn("failing tests", res["message"])
            self.assertEqual(plan.status, UpgradeStatus.FAILED)
            # Verify file was rolled back to original text
            self.assertEqual(target.read_text(encoding="utf-8"), orig_text)

    # 6. REST API Endpoints Tests
    def test_api_diagnose(self):
        res = self.client.get("/api/self-upgrade/diagnose")
        self.assertEqual(res.status_code, 200)
        self.assertIn("diagnostic", res.get_json())

    def test_api_plan_creation_and_block_protected_file(self):
        res = self.client.post("/api/self-upgrade/plan", json={
            "reason": "Modify environment secrets",
            "files": [".env"]
        })
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json()["status"], "blocked")

    def test_api_plan_creation_success(self):
        res = self.client.post("/api/self-upgrade/plan", json={
            "reason": "Upgrade response validation",
            "files": ["intelligence/evaluator.py"]
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("upgrade_id", data["plan"])

    def test_api_upgrade_history(self):
        res = self.client.get("/api/self-upgrade/history")
        self.assertEqual(res.status_code, 200)
        self.assertIn("history", res.get_json())


if __name__ == "__main__":
    unittest.main()
