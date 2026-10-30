"""
Upgrade Planning Engine for TONY AI Self-Upgrade Subsystem.
Produces structured, risk-assessed UpgradePlan instances with file diffs and affected tests.
"""
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import uuid
import logging

from self_upgrade.models import UpgradePlan, UpgradeStep, RiskLevel, UpgradeStatus
from self_upgrade.policy import UpgradeSecurityPolicy

logger = logging.getLogger("tony.self_upgrade.planner")


class UpgradePlanner:
    """Formulates structured, reviewable upgrade plans with risk calculations."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def create_plan(
        self,
        reason: str,
        files_to_modify: List[str],
        proposed_changes: Optional[Dict[str, str]] = None,
        risk_level: Optional[RiskLevel] = None
    ) -> UpgradePlan:
        """
        Construct a structured UpgradePlan.
        """
        # Validate all file paths against security policy
        for rel_path in files_to_modify:
            UpgradeSecurityPolicy.validate_target_path(rel_path, self.project_root)

        steps: List[UpgradeStep] = []
        changes = proposed_changes or {}

        for idx, file_path in enumerate(files_to_modify):
            full_path = self.project_root / file_path
            orig_content = full_path.read_text(encoding="utf-8", errors="replace") if full_path.exists() else ""
            new_content = changes.get(file_path, orig_content)

            steps.append(UpgradeStep(
                step_id=f"step_{idx + 1}",
                file_path=file_path,
                description=f"Update {file_path} for {reason}",
                content=new_content,
                original_content=orig_content,
                applied=False
            ))

        # Risk calculation
        assessed_risk = risk_level or self._assess_risk(files_to_modify)
        tests_count = self._estimate_affected_tests(files_to_modify)

        uid = f"upg_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        plan = UpgradePlan(
            upgrade_id=uid,
            reason=reason,
            files_changed=files_to_modify,
            steps=steps,
            risk_level=assessed_risk,
            tests_affected=tests_count,
            requires_confirmation=True,
            status=UpgradeStatus.PLANNED,
            created_at=datetime.now().isoformat()
        )

        logger.info(f"Formulated UpgradePlan '{plan.upgrade_id}' (Risk: {plan.risk_level.value}, Files: {len(plan.files_changed)})")
        return plan

    def _assess_risk(self, files: List[str]) -> RiskLevel:
        """Estimate modification risk based on file sensitivity and scope."""
        core_files = ["app.py", "intelligence/orchestrator.py", "config/settings.py", "agent/executor.py"]
        if any(f in core_files for f in files):
            return RiskLevel.MEDIUM
        if len(files) > 4:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _estimate_affected_tests(self, files: List[str]) -> int:
        """Estimate the number of test suites affected by the changes."""
        affected = 0
        tests_dir = self.project_root / "tests"
        if tests_dir.exists():
            for t_file in tests_dir.glob("test_*.py"):
                affected += 1
        return max(affected, 1)
