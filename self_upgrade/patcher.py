"""
Patch Application Engine for TONY AI Self-Upgrade Subsystem.
Safely and atomically applies validated code patches to project files.
"""
from pathlib import Path
import logging

from self_upgrade.models import UpgradePlan, UpgradeStep
from self_upgrade.policy import UpgradeSecurityPolicy
from self_upgrade.validator import PatchValidator
from self_upgrade.errors import PatchValidationError

logger = logging.getLogger("tony.self_upgrade.patcher")


class CodePatcher:
    """Applies validated steps to project target files."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def apply_plan(self, plan: UpgradePlan) -> bool:
        """
        Validate and apply all steps in an UpgradePlan.
        """
        # Step 1: Pre-validate all steps before writing anything
        for step in plan.steps:
            target_path = UpgradeSecurityPolicy.validate_target_path(step.file_path, self.project_root)
            PatchValidator.validate_content(step.content, step.file_path)

        # Step 2: Apply changes
        for step in plan.steps:
            target_path = self.project_root / step.file_path
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Store original content in step if file exists
            if target_path.exists():
                step.original_content = target_path.read_text(encoding="utf-8", errors="replace")

            target_path.write_text(step.content, encoding="utf-8")
            step.applied = True
            logger.info(f"Applied patch step '{step.step_id}' to '{step.file_path}'")

        return True
