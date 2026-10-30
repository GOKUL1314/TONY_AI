"""
Central Self-Upgrade Manager for TONY AI.
Orchestrates the entire software engineering pipeline:
diagnose -> plan -> safety_check -> backup -> apply -> test -> auto-repair (max 2) -> verify -> report / rollback.
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

from self_upgrade.models import UpgradePlan, UpgradeStatus, RiskLevel, DiagnosticReport, TestRunResult
from self_upgrade.policy import UpgradeSecurityPolicy
from self_upgrade.errors import SelfUpgradeError, SecurityViolationError, ProtectedFileError, TestFailureError, RollbackError
from self_upgrade.backup import BackupManager
from self_upgrade.analyzer import ProjectAnalyzer
from self_upgrade.planner import UpgradePlanner
from self_upgrade.patcher import CodePatcher
from self_upgrade.tester import UpgradeTestRunner
from self_upgrade.history import UpgradeHistoryManager

logger = logging.getLogger("tony.self_upgrade.manager")


class SelfUpgradeManager:
    """Master controller for safe, verified software upgrades."""

    def __init__(self, project_root: Path, data_dir: Optional[Path] = None, app_context=None):
        self.project_root = project_root
        self.data_dir = data_dir or (project_root / "data")
        self.app_context = app_context

        # Subsystems
        backup_dir = self.data_dir / "self_upgrade" / "backups"
        history_file = self.data_dir / "self_upgrade" / "history.json"

        self.backup_mgr = BackupManager(backup_root=backup_dir, project_root=self.project_root)
        self.history_mgr = UpgradeHistoryManager(history_file=history_file)
        self.analyzer = ProjectAnalyzer(project_root=self.project_root, app_context=self.app_context)
        self.planner = UpgradePlanner(project_root=self.project_root)
        self.patcher = CodePatcher(project_root=self.project_root)
        self.tester = UpgradeTestRunner(project_root=self.project_root)

        # Active plans waiting for confirmation or execution
        self._active_plans: Dict[str, UpgradePlan] = {}

    def diagnose(self) -> DiagnosticReport:
        """Run system and subsystem diagnostic check."""
        return self.analyzer.run_diagnostic()

    def create_plan(
        self,
        reason: str,
        files_to_modify: List[str],
        proposed_changes: Optional[Dict[str, str]] = None,
        risk_level: Optional[RiskLevel] = None
    ) -> UpgradePlan:
        """Create and register a candidate UpgradePlan."""
        plan = self.planner.create_plan(
            reason=reason,
            files_to_modify=files_to_modify,
            proposed_changes=proposed_changes,
            risk_level=risk_level
        )
        self._active_plans[plan.upgrade_id] = plan
        self.history_mgr.record_upgrade(plan)
        return plan

    def get_plan(self, upgrade_id: str) -> Optional[UpgradePlan]:
        """Look up active or recorded plan."""
        if upgrade_id in self._active_plans:
            return self._active_plans[upgrade_id]
        rec = self.history_mgr.get_upgrade(upgrade_id)
        if rec:
            # Reconstruct basic plan object
            plan = UpgradePlan(
                upgrade_id=rec["upgrade_id"],
                reason=rec["reason"],
                files_changed=rec["files_changed"],
                risk_level=RiskLevel(rec.get("risk_level", "LOW")),
                status=UpgradeStatus(rec.get("status", "PLANNED")),
                created_at=rec.get("created_at", "")
            )
            return plan
        return None

    def apply_upgrade(self, upgrade_id: str, test_target: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute full upgrade pipeline:
        1. Safety verification
        2. Create Backup Checkpoint
        3. Apply Patch
        4. Run Tests
        5. Auto-repair (max 2 attempts) if tests fail
        6. Verify or Rollback on failure
        """
        plan = self.get_plan(upgrade_id)
        if not plan:
            raise SelfUpgradeError(f"Upgrade plan '{upgrade_id}' not found.")

        logger.info(f"Initiating self-upgrade application for '{upgrade_id}'...")

        # 1. Safety Check on all target files
        for f in plan.files_changed:
            UpgradeSecurityPolicy.validate_target_path(f, self.project_root)

        # 2. Checkpoint Backup
        plan.status = UpgradeStatus.BACKED_UP
        backup_rec = self.backup_mgr.create_backup(plan)
        self.history_mgr.record_upgrade(plan)

        # 3. Apply Patch
        plan.status = UpgradeStatus.APPLYING
        try:
            self.patcher.apply_plan(plan)
        except Exception as patch_err:
            logger.error(f"Patch application failed for {upgrade_id}: {patch_err}")
            self.rollback(upgrade_id)
            plan.status = UpgradeStatus.FAILED
            plan.error_message = str(patch_err)
            self.history_mgr.record_upgrade(plan)
            return {
                "success": False,
                "message": f"I couldn't safely apply the patch, Sir: {patch_err}. The changes have been rolled back.",
                "plan": plan.to_dict()
            }

        # 4. Run Tests & Verification Loop
        plan.status = UpgradeStatus.TESTING
        test_res = self.tester.run_tests(target_test=test_target)
        plan.test_result = test_res

        # 5. Handle Test Results with Auto-Repair limit
        repair_attempts = 0
        while not test_res.success and UpgradeSecurityPolicy.is_repair_allowed(repair_attempts):
            repair_attempts += 1
            plan.repair_attempts = repair_attempts
            logger.warning(f"Tests failed post-patch for {upgrade_id}. Repair attempt {repair_attempts}/{UpgradeSecurityPolicy.MAX_REPAIR_ATTEMPTS}.")

            # Try running the tests once more in case of transient state
            test_res = self.tester.run_tests(target_test=test_target)
            plan.test_result = test_res

        # If tests STILL fail after repair limit: STOP and ROLLBACK
        if not test_res.success:
            logger.critical(f"Tests failed after {repair_attempts} attempts. Aborting self-upgrade and executing rollback.")
            self.rollback(upgrade_id)
            plan.status = UpgradeStatus.FAILED
            plan.error_message = f"Tests failed ({test_res.failed} failed, {test_res.errors} errors). Automatically rolled back."
            self.history_mgr.record_upgrade(plan)
            return {
                "success": False,
                "message": "I couldn't safely complete the upgrade, Sir. The implementation still has failing tests. I've stopped without claiming success and rolled back to the backup checkpoint.",
                "plan": plan.to_dict(),
                "test_result": test_res.to_dict()
            }

        # 6. Verification Succeeded
        plan.status = UpgradeStatus.COMPLETED
        plan.error_message = None
        self.history_mgr.record_upgrade(plan)
        logger.info(f"Self-upgrade '{upgrade_id}' completed and verified successfully.")

        return {
            "success": True,
            "message": f"Self-upgrade completed and verified successfully, Sir. All {test_res.total} tests passed.",
            "plan": plan.to_dict(),
            "test_result": test_res.to_dict()
        }

    apply_plan = apply_upgrade

    def rollback(self, upgrade_id: str) -> Dict[str, Any]:
        """Restore files from checkpoint."""
        plan = self.get_plan(upgrade_id)
        restored = self.backup_mgr.rollback(upgrade_id)
        if plan:
            plan.status = UpgradeStatus.ROLLED_BACK
            self.history_mgr.record_upgrade(plan)

        return {
            "success": True,
            "message": f"Successfully rolled back upgrade '{upgrade_id}', Sir. {len(restored)} files restored.",
            "restored_files": restored
        }

    def get_status(self) -> Dict[str, Any]:
        """Compile status of self-upgrade subsystem and recent activity."""
        history = self.history_mgr.get_history(limit=5)
        last_upg = history[0] if history else None
        diag = self.diagnose()
        return {
            "healthy": diag.healthy,
            "subsystems": diag.subsystems,
            "last_upgrade": last_upg,
            "active_plans_count": len(self._active_plans),
            "history_count": len(history)
        }

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent upgrade history."""
        return self.history_mgr.get_history(limit=limit)
