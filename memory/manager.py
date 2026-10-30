"""
High-level Long-Term Memory Manager for TONY (Stage 4).
Handles CRUD, deduplication, superseding preferences, search, and category indexing.
"""
from datetime import datetime
import logging
from typing import Any
from memory.database import MemoryDatabase
from memory.models import MemoryItem

logger = logging.getLogger("tony.memory.manager")


class MemoryManager:
    """
    Coordinates persistent memory storage, deduplication, updates, and retrieval.
    """

    def __init__(self, db: MemoryDatabase | None = None, database: MemoryDatabase | None = None):
        self.db = db if db is not None else database
        if self.db is None:
            raise ValueError("MemoryManager requires a valid MemoryDatabase instance.")

    def save_memory(
        self,
        memory_key: str,
        memory_value: str,
        category: str = "other",
        importance: int = 2,
        source: str = "explicit"
    ) -> MemoryItem:
        """
        Store a memory with automatic deduplication and superseding logic.

        - If a memory with the exact key and value exists: updates access timestamps.
        - If a memory with the same key but different value exists: supersedes with new value.
        - Otherwise creates a new memory record.
        """
        clean_key = memory_key.strip().lower()
        clean_val = memory_value.strip()
        clean_cat = category.strip().lower() or "other"
        now = datetime.now().isoformat()

        # 1. Check for existing active memory with matching key
        existing = self.db.fetchone(
            "SELECT * FROM memories WHERE LOWER(memory_key) = ? AND is_active = 1",
            (clean_key,)
        )

        if existing:
            item = MemoryItem.from_row(existing)
            if item.memory_value.strip().lower() == clean_val.lower():
                # Duplicate: Update access count and timestamp
                new_count = item.access_count + 1
                self.db.execute(
                    """
                    UPDATE memories 
                    SET last_accessed_at = ?, access_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, new_count, now, item.id)
                )
                logger.info(f"Deduplicated memory #{item.id} ['{clean_key}']. Incremented access count to {new_count}.")
                item.access_count = new_count
                item.last_accessed_at = now
                item.updated_at = now
                return item
            else:
                # Value updated / superseded (e.g. user changed favorite language)
                new_importance = max(item.importance, importance)
                self.db.execute(
                    """
                    UPDATE memories 
                    SET memory_value = ?, category = ?, importance = ?, updated_at = ?, last_accessed_at = ?, access_count = access_count + 1
                    WHERE id = ?
                    """,
                    (clean_val, clean_cat, new_importance, now, now, item.id)
                )
                logger.info(f"Superseded memory #{item.id} ['{clean_key}'] from '{item.memory_value}' to '{clean_val}'.")
                item.memory_value = clean_val
                item.category = clean_cat
                item.importance = new_importance
                item.updated_at = now
                item.last_accessed_at = now
                item.access_count += 1
                return item

        # 2. Check if identical value already exists under different key in same category
        existing_val = self.db.fetchone(
            "SELECT * FROM memories WHERE LOWER(memory_value) = ? AND category = ? AND is_active = 1",
            (clean_val.lower(), clean_cat)
        )
        if existing_val:
            item = MemoryItem.from_row(existing_val)
            self.db.execute(
                "UPDATE memories SET last_accessed_at = ?, access_count = access_count + 1 WHERE id = ?",
                (now, item.id)
            )
            item.access_count += 1
            item.last_accessed_at = now
            return item

        # 3. Insert new memory
        row_id = self.db.execute(
            """
            INSERT INTO memories (
                memory_key, memory_value, category, importance, source,
                created_at, updated_at, last_accessed_at, access_count, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (clean_key, clean_val, clean_cat, importance, source, now, now, now, 1, 1)
        )

        logger.info(f"Saved new long-term memory #{row_id}: [{clean_cat}] '{clean_key}' -> '{clean_val}' (importance: {importance})")
        return MemoryItem(
            id=row_id,
            memory_key=clean_key,
            memory_value=clean_val,
            category=clean_cat,
            importance=importance,
            source=source,
            created_at=now,
            updated_at=now,
            last_accessed_at=now,
            access_count=1,
            is_active=True
        )

    def get_memory(self, memory_id: int) -> MemoryItem | None:
        """Fetch memory by its primary key ID."""
        row = self.db.fetchone("SELECT * FROM memories WHERE id = ?", (memory_id,))
        return MemoryItem.from_row(row) if row else None

    def get_by_key(self, memory_key: str, active_only: bool = True) -> MemoryItem | None:
        """Fetch memory by key."""
        sql = "SELECT * FROM memories WHERE LOWER(memory_key) = ?"
        params = [memory_key.strip().lower()]
        if active_only:
            sql += " AND is_active = 1"
        row = self.db.fetchone(sql, tuple(params))
        return MemoryItem.from_row(row) if row else None

    def update_memory(self, memory_id: int, updates: dict[str, Any]) -> MemoryItem | None:
        """Update fields of an existing memory."""
        item = self.get_memory(memory_id)
        if not item:
            return None

        allowed_fields = ["memory_key", "memory_value", "category", "importance", "is_active"]
        set_clauses = ["updated_at = ?"]
        params = [datetime.now().isoformat()]

        for field in allowed_fields:
            if field in updates:
                val = updates[field]
                if field == "importance":
                    val = max(1, min(5, int(val)))
                elif field == "is_active":
                    val = 1 if val else 0
                set_clauses.append(f"{field} = ?")
                params.append(val)

        params.append(memory_id)
        self.db.execute(f"UPDATE memories SET {', '.join(set_clauses)} WHERE id = ?", tuple(params))
        return self.get_memory(memory_id)

    def delete_memory(self, memory_id: int, hard_delete: bool = False) -> bool:
        """
        Delete a memory. Soft-deletes (is_active=0) by default to maintain historical integrity.
        """
        if hard_delete:
            rows = self.db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        else:
            now = datetime.now().isoformat()
            rows = self.db.execute(
                "UPDATE memories SET is_active = 0, updated_at = ? WHERE id = ?",
                (now, memory_id)
            )
        logger.info(f"Deleted memory #{memory_id} (hard_delete={hard_delete})")
        return rows > 0

    def forget_by_pattern(self, pattern: str) -> list[int]:
        """
        Deactivate memories matching a keyword or phrase (e.g. 'forget python').
        Returns list of deactivated memory IDs.
        """
        clean_pat = f"%{pattern.strip().lower()}%"
        matches = self.db.fetchall(
            """
            SELECT id FROM memories 
            WHERE is_active = 1 AND (LOWER(memory_key) LIKE ? OR LOWER(memory_value) LIKE ?)
            """,
            (clean_pat, clean_pat)
        )
        deactivated = []
        now = datetime.now().isoformat()
        for row in matches:
            mid = row["id"]
            self.db.execute("UPDATE memories SET is_active = 0, updated_at = ? WHERE id = ?", (now, mid))
            deactivated.append(mid)
        logger.info(f"Forgot {len(deactivated)} memories matching pattern: '{pattern}'")
        return deactivated

    def clear_all_memories(self, hard_delete: bool = False) -> int:
        """Clear all memories."""
        if hard_delete:
            count = self.db.execute("DELETE FROM memories")
        else:
            now = datetime.now().isoformat()
            count = self.db.execute("UPDATE memories SET is_active = 0, updated_at = ?", (now,))
        logger.info(f"Cleared all memories (hard_delete={hard_delete}, affected={count})")
        return count

    def list_memories(
        self,
        category: str | None = None,
        is_active: bool = True,
        limit: int = 100,
        offset: int = 0
    ) -> list[MemoryItem]:
        """List memories with optional category filtering and pagination."""
        sql = "SELECT * FROM memories WHERE is_active = ?"
        params: list[Any] = [1 if is_active else 0]

        if category and category.lower() != "all":
            sql += " AND LOWER(category) = ?"
            params.append(category.strip().lower())

        sql += " ORDER BY importance DESC, updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.db.fetchall(sql, tuple(params))
        return [MemoryItem.from_row(r) for r in rows]

    def search_memories(
        self,
        query: str,
        limit: int = 10,
        is_active: bool = True
    ) -> list[MemoryItem]:
        """
        Keyword and wildcard search across memory_key and memory_value.
        """
        clean = query.strip().lower()
        if not clean:
            return self.list_memories(is_active=is_active, limit=limit)

        tokens = clean.split()
        conditions = []
        params: list[Any] = [1 if is_active else 0]

        for token in tokens:
            pattern = f"%{token}%"
            conditions.append("(LOWER(memory_key) LIKE ? OR LOWER(memory_value) LIKE ? OR LOWER(category) LIKE ?)")
            params.extend([pattern, pattern, pattern])

        sql = f"""
        SELECT * FROM memories 
        WHERE is_active = ? AND ({' OR '.join(conditions)})
        ORDER BY importance DESC, updated_at DESC LIMIT ?
        """
        params.append(limit)

        rows = self.db.fetchall(sql, tuple(params))
        return [MemoryItem.from_row(r) for r in rows]

    def touch_memory(self, memory_id: int) -> None:
        """Mark memory as accessed during conversational recall."""
        now = datetime.now().isoformat()
        self.db.execute(
            "UPDATE memories SET last_accessed_at = ?, access_count = access_count + 1 WHERE id = ?",
            (now, memory_id)
        )

    def remember(
        self,
        key: str,
        value: str,
        category: str = "other",
        importance: int = 2,
        source: str = "explicit"
    ) -> MemoryItem:
        """Alias for save_memory."""
        return self.save_memory(
            memory_key=key,
            memory_value=value,
            category=category,
            importance=importance,
            source=source
        )

    def get_all(self, include_inactive: bool = False, limit: int = 100) -> list[MemoryItem]:
        """Fetch all memories, with option to include inactive items."""
        return self.list_memories(is_active=not include_inactive, limit=limit)

    def forget_by_key(self, key: str) -> bool:
        """Deactivate memory by key name."""
        deactivated = self.forget_by_pattern(key)
        return len(deactivated) > 0

    def clear_all(self, hard_delete: bool = False) -> int:
        """Alias for clear_all_memories."""
        return self.clear_all_memories(hard_delete=hard_delete)

    def search(self, query: str, limit: int = 10) -> list[MemoryItem]:
        """Alias for search_memories."""
        return self.search_memories(query=query, limit=limit)

    def get_stats(self) -> dict[str, Any]:
        """Return diagnostic metrics about stored long-term memory."""
        total = self.db.fetchone("SELECT COUNT(*) as count FROM memories")
        active = self.db.fetchone("SELECT COUNT(*) as count FROM memories WHERE is_active = 1")
        categories_data = self.db.fetchall(
            "SELECT category, COUNT(*) as count FROM memories WHERE is_active = 1 GROUP BY category"
        )
        last_rec = self.db.fetchone("SELECT updated_at FROM memories ORDER BY updated_at DESC LIMIT 1")

        return {
            "total_memories": total["count"] if total else 0,
            "active_memories": active["count"] if active else 0,
            "categories": {r["category"]: r["count"] for r in categories_data} if categories_data else {},
            "last_updated": last_rec["updated_at"] if last_rec else None
        }
