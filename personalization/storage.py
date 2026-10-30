"""
Dedicated SQLite Storage Engine for TONY AI Personalization Subsystem (Stage 12).
Manages tables for profile, preferences, reminders, routines, notifications, and audit telemetry.
Strictly isolated from data/memory.db and data/knowledge/index/knowledge.db.
"""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, List, Optional

from personalization.models import (
    UserProfile,
    UserPreference,
    Reminder,
    ReminderStatus,
    RecurrenceType,
    Routine,
    RoutineStep,
    Notification,
    ProactiveSuggestion
)
from personalization.errors import PersonalizationError, ReminderNotFoundError

logger = logging.getLogger("tony.personalization.storage")


class PersonalizationDatabase:
    """SQLite database manager for personalization state and scheduled jobs."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def get_connection(self):
        """Context manager providing a transactional SQLite connection."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=15.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise PersonalizationError(f"Database operation failed: {e}") from e
        finally:
            conn.close()

    def _init_schema(self):
        """Create database tables with indexes if not already existing."""
        with self.get_connection() as conn:
            # 1. Profile Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS profile (
                    id TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # 2. Preferences Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_preferences_cat ON preferences(category);")

            # 3. Reminders Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    scheduled_time TEXT NOT NULL,
                    recurrence TEXT NOT NULL,
                    recurrence_interval_days INTEGER,
                    timezone TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    last_triggered_at TEXT,
                    next_trigger_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_trigger ON reminders(enabled, next_trigger_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);")

            # 4. Routines Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS routines (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    steps_json TEXT NOT NULL,
                    schedule_time TEXT,
                    recurrence TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # 5. Notifications Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    delivered_at TEXT NOT NULL,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT,
                    source_type TEXT NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_notif_delivered ON notifications(delivered_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_notif_read ON notifications(is_read);")

            # 6. Proactive Suggestions Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS proactive_suggestions (
                    id TEXT PRIMARY KEY,
                    suggestion_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    proposed_action_json TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    cooldown_until TEXT
                );
            """)

            # 7. Audit Logging Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(created_at);")

        logger.info(f"Initialized Personalization SQLite schema at: {self.db_path}")

    # =========================================================================
    # Profile Operations
    # =========================================================================

    def get_profile(self) -> UserProfile:
        """Load user profile or default if uninitialized."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT data_json FROM profile WHERE id = 'user_profile';").fetchone()
            if row:
                try:
                    data = json.loads(row["data_json"])
                    return UserProfile.from_dict(data)
                except Exception as e:
                    logger.warning(f"Error parsing stored profile JSON: {e}")
        return UserProfile()

    def save_profile(self, profile: UserProfile) -> UserProfile:
        """Persist user profile updates."""
        profile.updated_at = datetime.now().isoformat()
        data_json = json.dumps(profile.to_dict())
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO profile (id, data_json, updated_at)
                VALUES ('user_profile', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    data_json = excluded.data_json,
                    updated_at = excluded.updated_at;
            """, (data_json, profile.updated_at))
        return profile

    def reset_profile(self) -> UserProfile:
        """Reset user profile to default values."""
        default_profile = UserProfile()
        self.save_profile(default_profile)
        return default_profile

    # =========================================================================
    # Preference Operations
    # =========================================================================

    def get_preference(self, key: str) -> Optional[UserPreference]:
        """Fetch preference by key."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM preferences WHERE key = ?;", (key,)).fetchone()
            if row:
                return UserPreference(
                    key=row["key"],
                    value=json.loads(row["value_json"]),
                    category=row["category"],
                    source=row["source"],
                    confidence=row["confidence"],
                    updated_at=row["updated_at"]
                )
        return None

    def set_preference(self, pref: UserPreference) -> UserPreference:
        """Create or update a structured preference."""
        pref.updated_at = datetime.now().isoformat()
        val_json = json.dumps(pref.value)
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO preferences (key, value_json, category, source, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    category = excluded.category,
                    source = excluded.source,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at;
            """, (pref.key, val_json, pref.category, pref.source, pref.confidence, pref.updated_at))
        return pref

    def delete_preference(self, key: str) -> bool:
        """Delete a preference by key."""
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM preferences WHERE key = ?;", (key,))
            return cur.rowcount > 0

    def list_preferences(self, category: Optional[str] = None) -> List[UserPreference]:
        """List all preferences, optionally filtered by category."""
        query = "SELECT * FROM preferences"
        params = ()
        if category:
            query += " WHERE category = ?"
            params = (category,)
        query += " ORDER BY category ASC, key ASC;"

        results = []
        with self.get_connection() as conn:
            for row in conn.execute(query, params).fetchall():
                results.append(UserPreference(
                    key=row["key"],
                    value=json.loads(row["value_json"]),
                    category=row["category"],
                    source=row["source"],
                    confidence=row["confidence"],
                    updated_at=row["updated_at"]
                ))
        return results

    def clear_preferences(self) -> int:
        """Clear all stored preferences."""
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM preferences;")
            return cur.rowcount

    # =========================================================================
    # Reminder Operations
    # =========================================================================

    def save_reminder(self, reminder: Reminder) -> Reminder:
        """Create or update a reminder record."""
        reminder.updated_at = datetime.now().isoformat()
        rec_val = reminder.recurrence.value if isinstance(reminder.recurrence, RecurrenceType) else str(reminder.recurrence)
        st_val = reminder.status.value if isinstance(reminder.status, ReminderStatus) else str(reminder.status)

        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO reminders (
                    id, title, description, scheduled_time, recurrence,
                    recurrence_interval_days, timezone, enabled, status,
                    last_triggered_at, next_trigger_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    scheduled_time = excluded.scheduled_time,
                    recurrence = excluded.recurrence,
                    recurrence_interval_days = excluded.recurrence_interval_days,
                    timezone = excluded.timezone,
                    enabled = excluded.enabled,
                    status = excluded.status,
                    last_triggered_at = excluded.last_triggered_at,
                    next_trigger_at = excluded.next_trigger_at,
                    updated_at = excluded.updated_at;
            """, (
                reminder.id, reminder.title, reminder.description,
                reminder.scheduled_time, rec_val, reminder.recurrence_interval_days,
                reminder.timezone, 1 if reminder.enabled else 0, st_val,
                reminder.last_triggered_at, reminder.next_trigger_at,
                reminder.created_at, reminder.updated_at
            ))
        return reminder

    def get_reminder(self, reminder_id: str) -> Optional[Reminder]:
        """Fetch reminder by ID."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM reminders WHERE id = ?;", (reminder_id,)).fetchone()
            if row:
                return self._row_to_reminder(row)
        return None

    def list_reminders(
        self,
        enabled_only: bool = False,
        status: Optional[str] = None
    ) -> List[Reminder]:
        """List reminders matching criteria."""
        query = "SELECT * FROM reminders WHERE 1=1"
        params = []
        if enabled_only:
            query += " AND enabled = 1"
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY next_trigger_at ASC, scheduled_time ASC;"

        with self.get_connection() as conn:
            return [self._row_to_reminder(r) for r in conn.execute(query, tuple(params)).fetchall()]

    def get_due_reminders(self, current_time_iso: str) -> List[Reminder]:
        """Find enabled reminders whose next_trigger_at is due (<= current_time)."""
        query = """
            SELECT * FROM reminders
            WHERE enabled = 1
              AND status IN ('pending', 'snoozed')
              AND next_trigger_at IS NOT NULL
              AND next_trigger_at <= ?
            ORDER BY next_trigger_at ASC;
        """
        with self.get_connection() as conn:
            return [self._row_to_reminder(r) for r in conn.execute(query, (current_time_iso,)).fetchall()]

    def delete_reminder(self, reminder_id: str) -> bool:
        """Permanently delete a reminder."""
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM reminders WHERE id = ?;", (reminder_id,))
            return cur.rowcount > 0

    def clear_reminders(self) -> int:
        """Clear all reminders."""
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM reminders;")
            return cur.rowcount

    def _row_to_reminder(self, row: sqlite3.Row) -> Reminder:
        """Helper to convert database row to Reminder instance."""
        try:
            rec = RecurrenceType(row["recurrence"])
        except Exception:
            rec = RecurrenceType.NONE
        try:
            st = ReminderStatus(row["status"])
        except Exception:
            st = ReminderStatus.PENDING

        return Reminder(
            id=row["id"],
            title=row["title"],
            description=row["description"] or "",
            scheduled_time=row["scheduled_time"],
            recurrence=rec,
            recurrence_interval_days=row["recurrence_interval_days"],
            timezone=row["timezone"],
            enabled=bool(row["enabled"]),
            status=st,
            last_triggered_at=row["last_triggered_at"],
            next_trigger_at=row["next_trigger_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    # =========================================================================
    # Routine Operations
    # =========================================================================

    def save_routine(self, routine: Routine) -> Routine:
        """Create or update a routine record."""
        routine.updated_at = datetime.now().isoformat()
        steps_json = json.dumps([s.to_dict() for s in routine.steps])
        rec_val = routine.recurrence.value if isinstance(routine.recurrence, RecurrenceType) else str(routine.recurrence)

        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO routines (
                    id, name, description, steps_json, schedule_time,
                    recurrence, enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    steps_json = excluded.steps_json,
                    schedule_time = excluded.schedule_time,
                    recurrence = excluded.recurrence,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at;
            """, (
                routine.id, routine.name, routine.description,
                steps_json, routine.schedule_time, rec_val,
                1 if routine.enabled else 0, routine.created_at, routine.updated_at
            ))
        return routine

    def get_routine(self, routine_id: str) -> Optional[Routine]:
        """Fetch routine by ID."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM routines WHERE id = ?;", (routine_id,)).fetchone()
            if row:
                return self._row_to_routine(row)
        return None

    def list_routines(self, enabled_only: bool = False) -> List[Routine]:
        """List defined routines."""
        query = "SELECT * FROM routines"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY name ASC;"

        with self.get_connection() as conn:
            return [self._row_to_routine(r) for r in conn.execute(query).fetchall()]

    def delete_routine(self, routine_id: str) -> bool:
        """Delete a routine by ID."""
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM routines WHERE id = ?;", (routine_id,))
            return cur.rowcount > 0

    def _row_to_routine(self, row: sqlite3.Row) -> Routine:
        """Helper to convert database row to Routine instance."""
        steps_data = json.loads(row["steps_json"]) if row["steps_json"] else []
        steps = [
            RoutineStep(
                step_id=s.get("step_id", ""),
                action_type=s.get("action_type", ""),
                parameters=s.get("parameters", {}),
                description=s.get("description", "")
            )
            for s in steps_data
        ]
        try:
            rec = RecurrenceType(row["recurrence"])
        except Exception:
            rec = RecurrenceType.NONE

        return Routine(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            steps=steps,
            schedule_time=row["schedule_time"],
            recurrence=rec,
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    # =========================================================================
    # Notifications Operations
    # =========================================================================

    def add_notification(self, notif: Notification) -> Notification:
        """Persist a notification delivery record."""
        meta_json = json.dumps(notif.metadata)
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO notifications (
                    id, title, message, channel, delivered_at, is_read, metadata_json, source_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                notif.id, notif.title, notif.message, notif.channel,
                notif.delivered_at, 1 if notif.is_read else 0, meta_json, notif.source_type
            ))
        return notif

    def list_notifications(self, limit: int = 50, unread_only: bool = False) -> List[Notification]:
        """Fetch delivered notifications ordered newest first."""
        query = "SELECT * FROM notifications"
        if unread_only:
            query += " WHERE is_read = 0"
        query += " ORDER BY delivered_at DESC LIMIT ?;"

        results = []
        with self.get_connection() as conn:
            for row in conn.execute(query, (limit,)).fetchall():
                meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
                results.append(Notification(
                    id=row["id"],
                    title=row["title"],
                    message=row["message"],
                    channel=row["channel"],
                    delivered_at=row["delivered_at"],
                    is_read=bool(row["is_read"]),
                    metadata=meta,
                    source_type=row["source_type"]
                ))
        return results

    def mark_notification_read(self, notif_id: str) -> bool:
        """Mark notification as read."""
        with self.get_connection() as conn:
            cur = conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?;", (notif_id,))
            return cur.rowcount > 0

    def dismiss_all_notifications(self) -> int:
        """Mark all notifications as read / dismissed."""
        with self.get_connection() as conn:
            cur = conn.execute("UPDATE notifications SET is_read = 1;")
            return cur.rowcount

    def count_notifications_today(self, date_str: Optional[str] = None) -> int:
        """Count notifications delivered today (YYYY-MM-DD prefix)."""
        target_date = date_str or date.today().isoformat()
        pattern = f"{target_date}%"
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM notifications WHERE delivered_at LIKE ?;",
                (pattern,)
            ).fetchone()
            return row["cnt"] if row else 0

    # =========================================================================
    # Proactive Suggestions Operations
    # =========================================================================

    def add_suggestion(self, sugg: ProactiveSuggestion) -> ProactiveSuggestion:
        """Record a newly generated proactive suggestion."""
        action_json = json.dumps(sugg.proposed_action)
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO proactive_suggestions (
                    id, suggestion_type, title, description, proposed_action_json, status, created_at, cooldown_until
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                sugg.id, sugg.suggestion_type, sugg.title, sugg.description,
                action_json, sugg.status, sugg.created_at, sugg.cooldown_until
            ))
        return sugg

    def list_suggestions(self, status: Optional[str] = None, limit: int = 20) -> List[ProactiveSuggestion]:
        """List proactive suggestions."""
        query = "SELECT * FROM proactive_suggestions"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?;"
        params.append(limit)

        results = []
        with self.get_connection() as conn:
            for row in conn.execute(query, tuple(params)).fetchall():
                action = json.loads(row["proposed_action_json"]) if row["proposed_action_json"] else {}
                results.append(ProactiveSuggestion(
                    id=row["id"],
                    suggestion_type=row["suggestion_type"],
                    title=row["title"],
                    description=row["description"],
                    proposed_action=action,
                    status=row["status"],
                    created_at=row["created_at"],
                    cooldown_until=row["cooldown_until"]
                ))
        return results

    def update_suggestion_status(self, suggestion_id: str, status: str) -> bool:
        """Update suggestion status (accepted, rejected, expired)."""
        with self.get_connection() as conn:
            cur = conn.execute(
                "UPDATE proactive_suggestions SET status = ? WHERE id = ?;",
                (status, suggestion_id)
            )
            return cur.rowcount > 0

    # =========================================================================
    # Audit Logging & Health Telemetry
    # =========================================================================

    def log_audit(self, action: str, details: Dict[str, Any]):
        """Record audit event telemetry without logging sensitive tokens."""
        now = datetime.now().isoformat()
        det_json = json.dumps(details)
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT INTO audit_logs (action, details_json, created_at) VALUES (?, ?, ?);",
                    (action, det_json, now)
                )
        except Exception as e:
            logger.warning(f"Failed to record audit log: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate summary metrics for personalization subsystem."""
        with self.get_connection() as conn:
            pref_count = conn.execute("SELECT COUNT(*) AS c FROM preferences;").fetchone()["c"]
            rem_active = conn.execute("SELECT COUNT(*) AS c FROM reminders WHERE enabled = 1 AND status = 'pending';").fetchone()["c"]
            rem_total = conn.execute("SELECT COUNT(*) AS c FROM reminders;").fetchone()["c"]
            rtn_count = conn.execute("SELECT COUNT(*) AS c FROM routines;").fetchone()["c"]
            notif_today = self.count_notifications_today()
            notif_total = conn.execute("SELECT COUNT(*) AS c FROM notifications;").fetchone()["c"]

        return {
            "preferences_count": pref_count,
            "reminders_active": rem_active,
            "reminders_total": rem_total,
            "routines_count": rtn_count,
            "notifications_today": notif_today,
            "notifications_total": notif_total,
            "database_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0
        }

    def check_health(self) -> Dict[str, Any]:
        """Check operational status of SQLite storage engine."""
        try:
            with self.get_connection() as conn:
                conn.execute("SELECT 1;")
            return {
                "healthy": True,
                "database": "connected",
                "db_path": str(self.db_path)
            }
        except Exception as e:
            return {
                "healthy": False,
                "database": f"error: {e}",
                "db_path": str(self.db_path)
            }
