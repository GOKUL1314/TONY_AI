"""
Persistent Image History Manager for TONY AI (Stage 6).
Stores and manages metadata for all generated images in JSON format.
"""
import json
import logging
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any
from image_generation.models import ImageMetadata

logger = logging.getLogger("tony.image_generation.history")


class ImageHistoryManager:
    """Manages metadata records and persistence for generated images."""

    def __init__(self, history_file: Path, max_records: int = 100):
        self.history_file = Path(history_file)
        self.max_records = max_records
        self._lock = threading.Lock()
        self._records: List[ImageMetadata] = []
        self._load()

    def _load(self) -> None:
        """Load records from disk into memory."""
        with self._lock:
            if not self.history_file.exists():
                self._records = []
                return

            try:
                content = self.history_file.read_text(encoding="utf-8")
                if not content.strip():
                    self._records = []
                    return
                data = json.loads(content)
                if isinstance(data, list):
                    self._records = [ImageMetadata.from_dict(item) for item in data]
                else:
                    self._records = []
            except Exception as e:
                logger.error(f"Failed to load image history file: {e}")
                self._records = []

    def _save(self) -> None:
        """Save in-memory records to disk."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            data = [rec.to_dict() for rec in self._records]
            # Write atomically using temporary file
            tmp_path = self.history_file.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp_path.replace(self.history_file)
        except Exception as e:
            logger.error(f"Failed to save image history to disk: {e}")

    def add_record(self, metadata: ImageMetadata) -> None:
        """Add a new image metadata record to history (newest at the beginning)."""
        with self._lock:
            # Check for existing record by image_id
            self._records = [r for r in self._records if r.image_id != metadata.image_id]
            self._records.insert(0, metadata)
            # Enforce max records
            if len(self._records) > self.max_records:
                self._records = self._records[:self.max_records]
            self._save()

    def get_record(self, image_id: str) -> Optional[ImageMetadata]:
        """Retrieve a specific record by image_id."""
        with self._lock:
            for record in self._records:
                if record.image_id == image_id:
                    return record
            return None

    def list_records(self, limit: int = 50, offset: int = 0) -> List[ImageMetadata]:
        """List records with pagination."""
        with self._lock:
            return list(self._records[offset: offset + limit])

    def delete_record(self, image_id: str) -> bool:
        """Delete a record by image_id."""
        with self._lock:
            initial_count = len(self._records)
            self._records = [r for r in self._records if r.image_id != image_id]
            if len(self._records) < initial_count:
                self._save()
                return True
            return False

    def get_latest_record(self) -> Optional[ImageMetadata]:
        """Get the most recently generated image record."""
        with self._lock:
            return self._records[0] if self._records else None

    def count(self) -> int:
        """Return total number of recorded images."""
        with self._lock:
            return len(self._records)

    def clear_history(self) -> int:
        """Clear all metadata records."""
        with self._lock:
            count = len(self._records)
            self._records = []
            self._save()
            return count
