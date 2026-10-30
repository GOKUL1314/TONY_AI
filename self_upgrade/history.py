"""
Persistent History Tracker for TONY AI Self-Upgrade Subsystem.
Maintains an immutable record of all diagnostic reports, proposed plans, and applied upgrades.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

from self_upgrade.models import UpgradePlan

logger = logging.getLogger("tony.self_upgrade.history")


class UpgradeHistoryManager:
    """Manages history storage in data/self_upgrade/history.json."""

    def __init__(self, history_file: Path):
        self.history_file = history_file
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.history_file.exists():
            self._save_raw([])

    def _load_raw(self) -> List[Dict[str, Any]]:
        try:
            if not self.history_file.exists():
                return []
            content = self.history_file.read_text(encoding="utf-8")
            if not content.strip():
                return []
            return json.loads(content)
        except Exception as e:
            logger.error(f"Error reading self-upgrade history: {e}")
            return []

    def _save_raw(self, records: List[Dict[str, Any]]) -> None:
        try:
            self.history_file.write_text(json.dumps(records, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Error writing self-upgrade history: {e}")

    def record_upgrade(self, plan: UpgradePlan) -> None:
        """Append or update an upgrade record in history without overwriting previous entries."""
        records = self._load_raw()
        existing_idx = next((i for i, r in enumerate(records) if r.get("upgrade_id") == plan.upgrade_id), None)
        entry = plan.to_dict()

        if existing_idx is not None:
            records[existing_idx] = entry
        else:
            records.append(entry)

        self._save_raw(records)
        logger.info(f"Recorded self-upgrade entry for '{plan.upgrade_id}' (Status: {plan.status.value})")

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent upgrade history records."""
        records = self._load_raw()
        # Sort descending by creation date
        records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return records[:limit]

    def get_upgrade(self, upgrade_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve specific upgrade record by ID."""
        records = self._load_raw()
        return next((r for r in records if r.get("upgrade_id") == upgrade_id), None)
