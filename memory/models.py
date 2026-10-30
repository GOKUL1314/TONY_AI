"""
Data models for TONY Long-Term Memory (Stage 4).
"""
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any


@dataclass
class MemoryItem:
    """
    Representation of an individual long-term memory entity.
    """
    memory_key: str
    memory_value: str
    category: str = "other"
    importance: int = 2  # 1 (low) to 5 (critical)
    source: str = "explicit"  # 'explicit', 'extracted', 'chat', 'voice'
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""
    last_accessed_at: str = ""
    access_count: int = 0
    is_active: bool = True

    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if not self.last_accessed_at:
            self.last_accessed_at = now
        # Clamp importance to range 1-5
        self.importance = max(1, min(5, int(self.importance)))

    @property
    def key(self) -> str:
        """Alias for memory_key."""
        return self.memory_key

    @property
    def value(self) -> str:
        """Alias for memory_value."""
        return self.memory_value

    def to_dict(self) -> dict[str, Any]:
        """Convert memory entity to dictionary format for JSON APIs."""
        d = asdict(self)
        d["key"] = self.memory_key
        d["value"] = self.memory_value
        d["is_active"] = bool(self.is_active)
        return d

    @classmethod
    def from_row(cls, row: dict[str, Any] | tuple) -> "MemoryItem":
        """Reconstruct a MemoryItem from a database row."""
        if isinstance(row, dict):
            return cls(
                id=row.get("id"),
                memory_key=row.get("memory_key", ""),
                memory_value=row.get("memory_value", ""),
                category=row.get("category", "other"),
                importance=row.get("importance", 2),
                source=row.get("source", "explicit"),
                created_at=row.get("created_at", ""),
                updated_at=row.get("updated_at", ""),
                last_accessed_at=row.get("last_accessed_at", ""),
                access_count=row.get("access_count", 0),
                is_active=bool(row.get("is_active", 1)),
            )

        # Handle tuple from standard cursor fetch
        return cls(
            id=row[0],
            memory_key=row[1],
            memory_value=row[2],
            category=row[3],
            importance=row[4],
            source=row[5],
            created_at=row[6],
            updated_at=row[7],
            last_accessed_at=row[8],
            access_count=row[9],
            is_active=bool(row[10]),
        )
