"""
Persistent Local Scheduler for TONY AI Personalization Subsystem (Stage 12).
Executes scheduled reminders and recurring workflows with timezone awareness,
idempotency, restart recovery, and safe background thread lifecycle.
"""
import uuid
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from personalization.models import (
    Reminder,
    ReminderStatus,
    RecurrenceType,
    Notification
)
from personalization.storage import PersonalizationDatabase
from personalization.notifications import NotificationService
from personalization.errors import SchedulerError, ReminderNotFoundError

logger = logging.getLogger("tony.personalization.scheduler")


class AutomationScheduler:
    """Threaded background scheduler managing persistent reminders and recurring jobs."""

    def __init__(
        self,
        db: PersonalizationDatabase,
        notification_service: NotificationService,
        check_interval_seconds: float = 5.0,
        default_timezone: str = "Asia/Kolkata"
    ):
        self.db = db
        self.notifications = notification_service
        self.check_interval = check_interval_seconds
        self.default_timezone = default_timezone

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._on_trigger_callbacks: List[Callable[[Reminder], None]] = []

    def register_trigger_callback(self, callback: Callable[[Reminder], None]):
        """Subscribe external listener to reminder trigger events."""
        if callback not in self._on_trigger_callbacks:
            self._on_trigger_callbacks.append(callback)

    def start(self):
        """Start the background scheduler thread."""
        if self._running:
            return

        self._stop_event.clear()
        self._running = True

        # Perform startup restart recovery
        self._handle_restart_recovery()

        self._thread = threading.Thread(
            target=self._scheduler_loop,
            name="TonySchedulerThread",
            daemon=True
        )
        self._thread.start()
        logger.info("Personalization Scheduler background thread started.")

    def stop(self, timeout: float = 3.0):
        """Safely terminate the background scheduler thread."""
        if not self._running:
            return
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._running = False
        logger.info("Personalization Scheduler background thread stopped.")

    def is_healthy(self) -> bool:
        """Check if scheduler thread is actively operating."""
        return self._running and (self._thread is not None and self._thread.is_alive())

    # =========================================================================
    # Reminder Management APIs
    # =========================================================================

    def create_reminder(
        self,
        title: str,
        scheduled_time: str | datetime,
        description: str = "",
        recurrence: RecurrenceType = RecurrenceType.NONE,
        interval_days: Optional[int] = None,
        timezone: Optional[str] = None
    ) -> Reminder:
        """Schedule a new reminder."""
        tz_str = timezone or self.default_timezone
        time_str = scheduled_time.isoformat() if isinstance(scheduled_time, datetime) else str(scheduled_time)

        rem_id = f"rem_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        reminder = Reminder(
            id=rem_id,
            title=title.strip(),
            description=description.strip(),
            scheduled_time=time_str,
            recurrence=recurrence,
            recurrence_interval_days=interval_days,
            timezone=tz_str,
            enabled=True,
            status=ReminderStatus.PENDING,
            next_trigger_at=time_str
        )

        saved = self.db.save_reminder(reminder)
        self.db.log_audit("reminder_created", {"id": rem_id, "title": title, "scheduled_time": time_str, "recurrence": str(recurrence)})
        logger.info(f"Scheduled reminder '{title}' (id: {rem_id}) for {time_str}")
        return saved

    def pause_reminder(self, reminder_id: str) -> Reminder:
        """Pause a pending reminder."""
        rem = self.db.get_reminder(reminder_id)
        if not rem:
            raise ReminderNotFoundError(f"Reminder '{reminder_id}' not found.")
        rem.status = ReminderStatus.PAUSED
        rem.enabled = False
        saved = self.db.save_reminder(rem)
        self.db.log_audit("reminder_paused", {"id": reminder_id})
        return saved

    def resume_reminder(self, reminder_id: str) -> Reminder:
        """Resume a paused reminder."""
        rem = self.db.get_reminder(reminder_id)
        if not rem:
            raise ReminderNotFoundError(f"Reminder '{reminder_id}' not found.")
        rem.status = ReminderStatus.PENDING
        rem.enabled = True
        # Recalculate next trigger if needed
        now_iso = self.get_now_iso(rem.timezone)
        if rem.next_trigger_at and rem.next_trigger_at < now_iso:
            rem.next_trigger_at = self.calculate_next_trigger(rem, from_time_iso=now_iso) or now_iso
        saved = self.db.save_reminder(rem)
        self.db.log_audit("reminder_resumed", {"id": reminder_id})
        return saved

    def snooze_reminder(self, reminder_id: str, minutes: int = 10) -> Reminder:
        """Snooze a reminder by adding N minutes to its trigger time."""
        rem = self.db.get_reminder(reminder_id)
        if not rem:
            raise ReminderNotFoundError(f"Reminder '{reminder_id}' not found.")
        tz = self._get_tz(rem.timezone)
        now = datetime.now(tz) if tz else datetime.now()
        snooze_dt = now + timedelta(minutes=max(1, minutes))
        rem.status = ReminderStatus.SNOOZED
        rem.enabled = True
        rem.next_trigger_at = snooze_dt.isoformat()
        saved = self.db.save_reminder(rem)
        self.db.log_audit("reminder_snoozed", {"id": reminder_id, "minutes": minutes, "new_time": rem.next_trigger_at})
        return saved

    def cancel_reminder(self, reminder_id: str) -> Reminder:
        """Mark a reminder as cancelled."""
        rem = self.db.get_reminder(reminder_id)
        if not rem:
            raise ReminderNotFoundError(f"Reminder '{reminder_id}' not found.")
        rem.status = ReminderStatus.CANCELLED
        rem.enabled = False
        rem.next_trigger_at = None
        saved = self.db.save_reminder(rem)
        self.db.log_audit("reminder_cancelled", {"id": reminder_id})
        return saved

    def get_reminder(self, reminder_id: str) -> Optional[Reminder]:
        """Fetch reminder by ID."""
        return self.db.get_reminder(reminder_id)

    def list_reminders(self, enabled_only: bool = False, status: Optional[str] = None) -> List[Reminder]:
        """List reminders from database."""
        return self.db.list_reminders(enabled_only=enabled_only, status=status)

    def delete_reminder(self, reminder_id: str) -> bool:
        """Permanently delete a reminder."""
        ok = self.db.delete_reminder(reminder_id)
        if ok:
            self.db.log_audit("reminder_deleted", {"id": reminder_id})
        return ok

    # Convenience aliases
    schedule_reminder = create_reminder

    def check_and_trigger_due_jobs(self, current_time_iso: Optional[str] = None) -> List[Reminder]:
        """Alias for trigger_due_jobs."""
        return self.trigger_due_jobs(current_time_iso)

    def _check_due_reminders(self, current_time_iso: Optional[str] = None) -> List[Reminder]:
        """Alias for trigger_due_jobs."""
        return self.trigger_due_jobs(current_time_iso)

    # =========================================================================
    # Scheduling Loop & Trigger Mechanics
    # =========================================================================

    def _scheduler_loop(self):
        """Worker loop checking for due reminders at regular intervals."""
        while not self._stop_event.is_set():
            try:
                self.trigger_due_jobs()
            except Exception as e:
                logger.error(f"Error in scheduler worker cycle: {e}", exc_info=True)
            self._stop_event.wait(self.check_interval)

    def trigger_due_jobs(self, current_time_iso: Optional[str] = None) -> List[Reminder]:
        """Check database and trigger all due reminders."""
        now_iso = current_time_iso or datetime.now().isoformat()
        due_reminders = self.db.get_due_reminders(now_iso)
        triggered = []

        for rem in due_reminders:
            try:
                self._execute_reminder(rem)
                triggered.append(rem)
            except Exception as e:
                logger.error(f"Error executing reminder {rem.id}: {e}")

        return triggered

    def _execute_reminder(self, rem: Reminder):
        """Idempotently trigger a single reminder and calculate next recurrence."""
        now_iso = datetime.now().isoformat()
        rem.last_triggered_at = now_iso

        # Dispatch notification
        alert_msg = rem.title
        if rem.description:
            alert_msg += f" — {rem.description}"

        try:
            self.notifications.send(
                title=f"Reminder: {rem.title}",
                message=alert_msg,
                source_type="reminder",
                metadata={"reminder_id": rem.id, "recurrence": str(rem.recurrence)},
                force_delivery=True
            )
        except Exception as e:
            logger.warning(f"Notification dispatch failed for reminder {rem.id}: {e}")

        # Notify callbacks
        for cb in self._on_trigger_callbacks:
            try:
                cb(rem)
            except Exception as cb_err:
                logger.warning(f"Error in reminder callback: {cb_err}")

        # Update recurrence or complete
        if rem.recurrence == RecurrenceType.NONE:
            rem.status = ReminderStatus.COMPLETED
            rem.enabled = False
            rem.next_trigger_at = None
        else:
            # Advance to next recurrence slot
            next_iso = self.calculate_next_trigger(rem, from_time_iso=now_iso)
            rem.next_trigger_at = next_iso
            rem.status = ReminderStatus.PENDING

        self.db.save_reminder(rem)
        self.db.log_audit("reminder_triggered", {"id": rem.id, "title": rem.title, "next": rem.next_trigger_at})
        logger.info(f"Triggered reminder '{rem.title}' (next trigger: {rem.next_trigger_at})")

    def calculate_next_trigger(self, rem: Reminder, from_time_iso: Optional[str] = None) -> Optional[str]:
        """Compute the next ISO timestamp based on recurrence rule."""
        tz = self._get_tz(rem.timezone)
        base_dt = datetime.fromisoformat(from_time_iso) if from_time_iso else datetime.now(tz)
        if base_dt.tzinfo is None and tz:
            base_dt = base_dt.replace(tzinfo=tz)

        rec = rem.recurrence
        if rec == RecurrenceType.NONE:
            return None

        if rec == RecurrenceType.DAILY:
            next_dt = base_dt + timedelta(days=1)
        elif rec == RecurrenceType.WEEKDAYS:
            # Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6
            weekday = base_dt.weekday()
            if weekday == 4:     # Friday -> Monday (+3)
                next_dt = base_dt + timedelta(days=3)
            elif weekday == 5:   # Saturday -> Monday (+2)
                next_dt = base_dt + timedelta(days=2)
            else:
                next_dt = base_dt + timedelta(days=1)
        elif rec == RecurrenceType.WEEKLY:
            next_dt = base_dt + timedelta(days=7)
        elif rec == RecurrenceType.MONTHLY:
            # Approximate next month (30 days) preserving hour/minute
            next_dt = base_dt + timedelta(days=30)
        elif rec == RecurrenceType.CUSTOM and rem.recurrence_interval_days:
            next_dt = base_dt + timedelta(days=max(1, rem.recurrence_interval_days))
        else:
            next_dt = base_dt + timedelta(days=1)

        return next_dt.isoformat()

    def _handle_restart_recovery(self):
        """Inspect stored reminders on startup to detect missed alerts during downtime."""
        now_iso = datetime.now().isoformat()
        missed = self.db.get_due_reminders(now_iso)
        if missed:
            logger.info(f"Scheduler restart recovery: found {len(missed)} reminders due during downtime.")
            for rem in missed:
                if rem.recurrence == RecurrenceType.NONE:
                    rem.status = ReminderStatus.MISSED
                    self.db.save_reminder(rem)
                    # Notify user of missed reminder
                    try:
                        self.notifications.send(
                            title=f"Missed Reminder: {rem.title}",
                            message=f"Scheduled for {rem.scheduled_time} (missed while offline).",
                            source_type="reminder_missed",
                            force_delivery=True
                        )
                    except Exception:
                        pass
                else:
                    # Recurring reminders catch up to next future slot
                    next_iso = self.calculate_next_trigger(rem, from_time_iso=now_iso)
                    rem.next_trigger_at = next_iso
                    self.db.save_reminder(rem)

    def get_now_iso(self, tz_name: Optional[str] = None) -> str:
        """Helper to get current ISO timestamp in target timezone."""
        tz = self._get_tz(tz_name or self.default_timezone)
        return (datetime.now(tz) if tz else datetime.now()).isoformat()

    def _get_tz(self, tz_name: Optional[str]):
        try:
            return ZoneInfo(tz_name or self.default_timezone)
        except Exception:
            return None
