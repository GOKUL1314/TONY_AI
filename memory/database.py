"""
SQLite Database connection and schema manager for TONY Long-Term Memory (Stage 4).
"""
from contextlib import contextmanager
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Any

logger = logging.getLogger("tony.memory.database")

# Thread-local storage for SQLite connections
_local = threading.local()


class MemoryDatabase:
    """
    Manages persistent SQLite connection, transactions, and schema for long-term memory.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local SQLite connection keyed by path."""
        connections = getattr(_local, "connections", None)
        if connections is None:
            connections = {}
            _local.connections = connections

        path_key = str(self.db_path)
        conn = connections.get(path_key)
        if conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=15.0,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            connections[path_key] = conn
        return conn

    @contextmanager
    def get_cursor(self):
        """Context manager yielding a cursor on the thread-local connection with auto-commit."""
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def _init_schema(self) -> None:
        """Initialize SQLite table and performance indexes."""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_key TEXT NOT NULL,
            memory_value TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'other',
            importance INTEGER NOT NULL DEFAULT 2,
            source TEXT NOT NULL DEFAULT 'explicit',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_accessed_at TEXT NOT NULL DEFAULT '',
            access_count INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(memory_key);
        CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
        CREATE INDEX IF NOT EXISTS idx_memories_active ON memories(is_active);
        CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);
        CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at);
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.executescript(schema_sql)
            logger.info(f"Initialized memory SQLite database schema at: {self.db_path}")
        except Exception as e:
            logger.exception(f"Failed to initialize memory database schema: {e}")
            raise

    def execute(self, query: str, params: tuple = ()) -> int:
        """Execute a modification query (INSERT, UPDATE, DELETE). Returns lastrowid or rowcount."""
        conn = self._get_connection()
        with conn:
            cursor = conn.execute(query, params)
            return cursor.lastrowid if cursor.lastrowid else cursor.rowcount

    def fetchone(self, query: str, params: tuple = ()) -> dict[str, Any] | None:
        """Fetch a single record as a dictionary."""
        conn = self._get_connection()
        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Fetch all matching records as dictionaries."""
        conn = self._get_connection()
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        """Close thread-local connection for this database path."""
        connections = getattr(_local, "connections", None)
        if connections:
            path_key = str(self.db_path)
            conn = connections.pop(path_key, None)
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
