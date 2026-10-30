"""
Central Orchestrator for TONY AI Personalization and Proactive Intelligence (Stage 12).
Integrates profile, preferences, reminders, routines, notifications, briefings,
scheduler lifecycle, and contextual dialogue personalization into a cohesive manager.
"""
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from personalization.models import (
    UserProfile,
    UserPreference,
    Reminder,
    RecurrenceType,
    Routine,
    BriefingData,
    Notification
)
from personalization.storage import PersonalizationDatabase
from personalization.profile import ProfileManager
from personalization.preferences import PreferencesManager
from personalization.time_parser import NaturalLanguageTimeParser
from personalization.policy import PersonalizationPolicy
from personalization.notifications import (
    NotificationService,
    InAppNotificationProvider,
    VoiceNotificationProvider
)
from personalization.scheduler import AutomationScheduler
from personalization.briefing import BriefingGenerator
from personalization.routines import RoutineManager
from personalization.context import PersonalizationContextBuilder
from personalization.errors import PersonalizationError, ReminderNotFoundError

logger = logging.getLogger("tony.personalization.manager")


class PersonalizationManager:
    """Master coordinator for all Stage 12 personalization capabilities."""

    def __init__(
        self,
        storage_dir: Path | str,
        tts_provider=None,
        agent_manager=None,
        ai_provider=None,
        default_timezone: str = "Asia/Kolkata",
        proactive_enabled: bool = False
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_dir / "personalization.db"

        # 1. Database layer
        self.db = PersonalizationDatabase(self.db_path)

        # 2. Subsystem Managers
        self.profile = ProfileManager(self.db)
        self.preferences = PreferencesManager(self.db)
        self.time_parser = NaturalLanguageTimeParser(default_timezone=default_timezone)

        # Sync initial proactive configuration to profile if unconfigured
        prof = self.profile.get_profile()
        if prof.proactive_mode != proactive_enabled and not prof.proactive_mode:
            prof.proactive_mode = proactive_enabled
            self.profile.update_profile({"proactive_mode": proactive_enabled})

        # 3. Notification Service
        in_app_prov = InAppNotificationProvider(self.db)
        voice_prov = VoiceNotificationProvider(tts_provider=tts_provider)
        self.notifications = NotificationService(self.db, providers=[in_app_prov, voice_prov])

        # 4. Automation Scheduler
        self.scheduler = AutomationScheduler(
            db=self.db,
            notification_service=self.notifications,
            check_interval_seconds=5.0,
            default_timezone=default_timezone
        )

        # 5. Briefing & Routines
        self.briefing = BriefingGenerator(
            db=self.db,
            agent_manager=agent_manager,
            ai_provider=ai_provider
        )
        self.routines = RoutineManager(self.db)

        # 6. Context Engine
        self.context_builder = PersonalizationContextBuilder(self.db)

        logger.info(f"Initialized PersonalizationManager at: {self.db_path} (Proactive: {prof.proactive_mode})")

    def start_scheduler(self):
        """Start the background reminder monitoring scheduler."""
        self.scheduler.start()

    def stop_scheduler(self):
        """Stop background scheduler."""
        self.scheduler.stop()

    # =========================================================================
    # Proactive Mode Toggles
    # =========================================================================

    def enable_proactive_mode(self) -> Dict[str, Any]:
        """Enable proactive assistant behavior."""
        self.profile.update_profile({"proactive_mode": True})
        self.db.log_audit("proactive_mode_enabled", {})
        return {
            "proactive_mode": True,
            "message": "Proactive mode is now enabled."
        }

    def disable_proactive_mode(self) -> Dict[str, Any]:
        """Disable proactive assistant behavior."""
        self.profile.update_profile({"proactive_mode": False})
        self.db.log_audit("proactive_mode_disabled", {})
        return {
            "proactive_mode": False,
            "message": "Proactive mode is now disabled."
        }

    def get_proactive_status(self) -> Dict[str, Any]:
        """Return the current proactive configuration and runtime status."""
        prof = self.profile.get_profile()
        sent_today = self.db.count_notifications_today()
        now = datetime.now()
        is_quiet = PersonalizationPolicy.is_quiet_hours(now, prof.quiet_hours_start, prof.quiet_hours_end)

        return {
            "proactive_mode": prof.proactive_mode,
            "enabled": prof.proactive_mode,
            "scheduler_healthy": self.scheduler.is_healthy(),
            "quiet_hours_active": is_quiet,
            "quiet_hours_start": prof.quiet_hours_start,
            "quiet_hours_end": prof.quiet_hours_end,
            "notifications_today": sent_today,
            "max_daily_notifications": prof.max_daily_notifications,
            "timezone": prof.timezone
        }

    # =========================================================================
    # Reminder Operations
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
        """Create and schedule a reminder."""
        clean_title = PersonalizationPolicy.sanitize_passive_text(title, "reminder title")
        clean_desc = PersonalizationPolicy.sanitize_passive_text(description, "reminder description") if description else ""

        return self.scheduler.create_reminder(
            title=clean_title,
            scheduled_time=scheduled_time,
            description=clean_desc,
            recurrence=recurrence,
            interval_days=interval_days,
            timezone=timezone
        )

    def create_reminder_from_text(self, text: str) -> Reminder:
        """
        Parse natural language reminder prompt (e.g. 'remind me in 10 minutes to drink water')
        and create corresponding scheduled reminder.
        """
        parsed = self.time_parser.parse(text)
        return self.create_reminder(
            title=parsed.extracted_title,
            scheduled_time=parsed.scheduled_time,
            description=f"Scheduled from: '{text}'",
            recurrence=parsed.recurrence,
            interval_days=parsed.recurrence_interval_days
        )

    def list_reminders(self, enabled_only: bool = False, status: Optional[str] = None) -> List[Reminder]:
        """List stored reminders."""
        return self.db.list_reminders(enabled_only=enabled_only, status=status)

    def get_reminder(self, reminder_id: str) -> Optional[Reminder]:
        """Fetch reminder by ID."""
        return self.db.get_reminder(reminder_id)

    def pause_reminder(self, reminder_id: str) -> Reminder:
        """Pause a pending reminder."""
        return self.scheduler.pause_reminder(reminder_id)

    def resume_reminder(self, reminder_id: str) -> Reminder:
        """Resume a paused reminder."""
        return self.scheduler.resume_reminder(reminder_id)

    def snooze_reminder(self, reminder_id: str, minutes: int = 10) -> Reminder:
        """Snooze a reminder by N minutes."""
        return self.scheduler.snooze_reminder(reminder_id, minutes=minutes)

    def cancel_reminder(self, reminder_id: str) -> Reminder:
        """Cancel a reminder."""
        return self.scheduler.cancel_reminder(reminder_id)

    def delete_reminder(self, reminder_id: str) -> bool:
        """Permanently delete a reminder."""
        return self.scheduler.delete_reminder(reminder_id)

    # =========================================================================
    # Briefing & Routines
    # =========================================================================

    def get_morning_briefing(self) -> BriefingData:
        """Generate today's morning briefing."""
        return self.briefing.generate_morning_briefing()

    def get_evening_summary(self) -> BriefingData:
        """Generate today's evening summary."""
        return self.briefing.generate_evening_summary()

    def list_routines(self, enabled_only: bool = False) -> List[Routine]:
        """List stored routines."""
        return self.routines.list_routines(enabled_only=enabled_only)

    def run_routine(self, routine_id: str, tool_executor=None) -> Dict[str, Any]:
        """Execute a routine by ID."""
        return self.routines.run_routine(
            routine_id=routine_id,
            briefing_generator=self.briefing,
            tool_executor=tool_executor,
            notification_service=self.notifications
        )

    # =========================================================================
    # Context & Chat Integration
    # =========================================================================

    def build_context(self, user_message: str) -> str:
        """Generate targeted personalization directives for the LLM prompt."""
        return self.context_builder.build_context(user_message)

    # =========================================================================
    # Safety & Reset
    # =========================================================================

    def reset_personalization(self) -> Dict[str, Any]:
        """Reset profile, clear preferences, and remove all reminders."""
        self.profile.reset_profile()
        p_count = self.preferences.clear_preferences()
        r_count = self.db.clear_reminders()
        self.db.log_audit("personalization_reset_completed", {"cleared_preferences": p_count, "cleared_reminders": r_count})
        return {
            "status": "success",
            "message": f"Personalization reset: profile restored to defaults, {p_count} preferences and {r_count} reminders cleared."
        }

    # =========================================================================
    # Telemetry & Health
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Subsystem metrics."""
        return self.db.get_stats()

    def check_health(self) -> Dict[str, Any]:
        """Health status of database, scheduler, and proactive services."""
        db_health = self.db.check_health()
        return {
            "healthy": db_health.get("healthy", False) and self.scheduler.is_healthy(),
            "database": db_health.get("database"),
            "scheduler": "healthy" if self.scheduler.is_healthy() else "stopped",
            "proactive_mode": self.profile.get_profile().proactive_mode,
            "reminders_count": self.db.get_stats().get("reminders_total", 0),
            "notifications_today": self.db.count_notifications_today()
        }
