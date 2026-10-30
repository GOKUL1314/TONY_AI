"""
Checkpoint and Backup Manager for TONY AI Self-Upgrade Subsystem.
Creates atomic checkpoints of targeted files before modification and handles rollbacks.
"""
from pathlib import Path
from datetime import datetime
import shutil
import logging
from typing import List

from self_upgrade.models import BackupRecord, UpgradePlan
from self_upgrade.errors import BackupError, RollbackError

logger = logging.getLogger("tony.self_upgrade.backup")


class BackupManager:
    """Manages file checkpoints under data/self_upgrade/backups/<upgrade_id>/."""

    def __init__(self, backup_root: Path, project_root: Path):
        self.backup_root = backup_root
        self.project_root = project_root
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def create_backup(self, plan: UpgradePlan) -> BackupRecord:
        """
        Create a timestamped directory backup of all files in the upgrade plan.
        """
        dest_dir = self.backup_root / plan.upgrade_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        backed_up_files: List[str] = []

        try:
            for rel_path in plan.files_changed:
                source_path = self.project_root / rel_path
                if source_path.exists():
                    target_backup_path = dest_dir / rel_path
                    target_backup_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, target_backup_path)
                    backed_up_files.append(rel_path)
                    logger.info(f"Backed up '{rel_path}' -> '{target_backup_path}'")

            plan.backup_location = str(dest_dir)
            return BackupRecord(
                upgrade_id=plan.upgrade_id,
                backup_dir=str(dest_dir),
                timestamp=datetime.now().isoformat(),
                files_backed_up=backed_up_files
            )
        except Exception as e:
            logger.error(f"Failed to create backup for {plan.upgrade_id}: {e}")
            raise BackupError(f"Could not create checkpoint backup: {e}")

    def rollback(self, upgrade_id: str) -> List[str]:
        """
        Restore original file contents from the checkpoint backup.
        """
        dest_dir = self.backup_root / upgrade_id
        if not dest_dir.exists():
            raise RollbackError(f"No backup checkpoint found for upgrade ID '{upgrade_id}'.")

        restored_files: List[str] = []
        try:
            for backup_file in dest_dir.rglob("*"):
                if backup_file.is_file():
                    rel_path = backup_file.relative_to(dest_dir)
                    project_dest = self.project_root / rel_path
                    project_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_file, project_dest)
                    restored_files.append(str(rel_path))
                    logger.info(f"Restored file '{rel_path}' from backup.")

            logger.info(f"Successfully rolled back upgrade '{upgrade_id}' ({len(restored_files)} files restored).")
            return restored_files
        except Exception as e:
            logger.error(f"Failed to restore checkpoint for {upgrade_id}: {e}")
            raise RollbackError(f"Rollback failed: {e}")
