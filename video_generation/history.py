"""
Thread-safe persistent video history manager for TONY AI (Stage 7).
Saves generation metadata, lineage, status, and parameters to JSON without storing secrets.
"""
import json
import logging
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any
from video_generation.models import VideoMetadata

logger = logging.getLogger("tony.video_generation.history")


class VideoHistoryManager:
    """Maintains thread-safe persistent history of generated video assets."""

    def __init__(self, history_file: Path, max_records: int = 100):
        self.history_file = Path(history_file).resolve()
        self.max_records = max_records
        self._lock = threading.Lock()
        self._records: List[VideoMetadata] = []
        self._load()

    def _load(self) -> None:
        """Load history from JSON file."""
        if not self.history_file.exists():
            self._records = []
            return

        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self._records = [VideoMetadata.from_dict(item) for item in data]
                else:
                    self._records = []
            logger.debug(f"Loaded {len(self._records)} video records from history.")
        except Exception as e:
            logger.error(f"Failed to load video history from '{self.history_file}': {e}")
            self._records = []

    def _save(self) -> None:
        """Persist current records to JSON file."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            data = [rec.to_dict() for rec in self._records]
            temp_file = self.history_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.history_file)
        except Exception as e:
            logger.error(f"Failed to save video history to '{self.history_file}': {e}")

    def add_record(self, record: VideoMetadata) -> None:
        """Add a video metadata record to history (newest first)."""
        with self._lock:
            # Avoid duplicate video_id
            self._records = [r for r in self._records if r.video_id != record.video_id]
            self._records.insert(0, record)
            # Enforce max records
            if len(self._records) > self.max_records:
                self._records = self._records[:self.max_records]
            self._save()

    def get_record(self, video_id: str) -> Optional[VideoMetadata]:
        """Retrieve record by video ID."""
        with self._lock:
            for r in self._records:
                if r.video_id == video_id:
                    return r
            return None

    def list_records(self, limit: int = 50, offset: int = 0) -> List[VideoMetadata]:
        """Retrieve paginated records."""
        with self._lock:
            return self._records[offset:offset + limit]

    def delete_record(self, video_id: str) -> bool:
        """Delete a record by video ID."""
        with self._lock:
            initial_len = len(self._records)
            self._records = [r for r in self._records if r.video_id != video_id]
            if len(self._records) < initial_len:
                self._save()
                return True
            return False

    def update_record(self, video_id: str, **kwargs) -> bool:
        """Update fields of an existing record."""
        with self._lock:
            for i, r in enumerate(self._records):
                if r.video_id == video_id:
                    r_dict = r.to_dict()
                    r_dict.update(kwargs)
                    self._records[i] = VideoMetadata.from_dict(r_dict)
                    self._save()
                    return True
            return False

    def get_latest_record(self) -> Optional[VideoMetadata]:
        """Get the most recently recorded video."""
        with self._lock:
            return self._records[0] if self._records else None

    def count(self) -> int:
        """Total count of recorded videos."""
        with self._lock:
            return len(self._records)

    def clear(self) -> None:
        """Clear all records."""
        with self._lock:
            self._records = []
            self._save()
