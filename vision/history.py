"""
History Manager for TONY AI Vision Subsystem (Stage 9).
Persists visual queries, results, and metadata in JSON format with thread safety.
"""
import json
import logging
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any
from vision.models import VisionResult

logger = logging.getLogger("tony.vision.history")


class VisionHistoryManager:
    """Manages persistent history for visual analysis requests."""

    def __init__(self, history_file: Path, max_records: int = 100):
        self.history_file = Path(history_file).resolve()
        self.max_records = max_records
        self._lock = threading.Lock()
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_history_file()

    def _ensure_history_file(self) -> None:
        if not self.history_file.exists():
            with self._lock:
                try:
                    self.history_file.write_text("[]", encoding="utf-8")
                except Exception as e:
                    logger.error(f"Failed to initialize vision history file: {e}")

    def add_record(self, result: VisionResult) -> None:
        """Append a new vision analysis result to history."""
        with self._lock:
            records = self._read_records_unlocked()
            # Insert at beginning for reverse-chronological order
            records.insert(0, result.to_dict())
            if len(records) > self.max_records:
                records = records[:self.max_records]
            self._write_records_unlocked(records)

    def get_record(self, vision_id: str) -> Optional[VisionResult]:
        """Fetch a specific vision result by vision_id."""
        with self._lock:
            records = self._read_records_unlocked()
            for r in records:
                if r.get("vision_id") == vision_id:
                    return VisionResult.from_dict(r)
        return None

    def get_latest_record(self) -> Optional[VisionResult]:
        """Retrieve the most recent visual analysis record."""
        with self._lock:
            records = self._read_records_unlocked()
            if records:
                return VisionResult.from_dict(records[0])
        return None

    def list_records(self, limit: int = 50) -> List[VisionResult]:
        """List visual analysis records up to specified limit."""
        with self._lock:
            records = self._read_records_unlocked()
            return [VisionResult.from_dict(r) for r in records[:limit]]

    def clear_history(self) -> None:
        """Clear all vision history records."""
        with self._lock:
            self._write_records_unlocked([])

    def _read_records_unlocked(self) -> List[Dict[str, Any]]:
        try:
            if not self.history_file.exists():
                return []
            content = self.history_file.read_text(encoding="utf-8")
            if not content.strip():
                return []
            data = json.loads(content)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to read vision history file: {e}")
            return []

    def _write_records_unlocked(self, records: List[Dict[str, Any]]) -> None:
        try:
            self.history_file.write_text(json.dumps(records, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write vision history file: {e}")
