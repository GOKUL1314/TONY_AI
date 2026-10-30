"""
Morning Briefing and Evening Summary Generator for TONY AI Personalization (Stage 12).
Synthesizes accurate, grounded daily digests exclusively from real system state.
Never hallucinates external calendar appointments, weather, or unverified emails.
"""
import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional

from personalization.models import BriefingData, UserProfile
from personalization.storage import PersonalizationDatabase

logger = logging.getLogger("tony.personalization.briefing")


class BriefingGenerator:
    """Generates authentic morning briefings and evening summaries from real system data."""

    def __init__(
        self,
        db: PersonalizationDatabase,
        agent_manager=None,
        ai_provider=None
    ):
        self.db = db
        self.agent_manager = agent_manager
        self.ai_provider = ai_provider

    def generate_morning_briefing(self, user_name: Optional[str] = None) -> BriefingData:
        """
        Produce a grounded morning briefing summarizing today's active items.
        """
        profile = self.db.get_profile()
        name = user_name or (profile.preferred_address if profile.preferred_address else profile.preferred_name) or "there"
        today_str = date.today().isoformat()

        # 1. Fetch today's reminders
        all_reminders = self.db.list_reminders(enabled_only=True)
        today_reminders = [
            r.to_dict() for r in all_reminders
            if (r.next_trigger_at and r.next_trigger_at.startswith(today_str))
            or (r.scheduled_time and r.scheduled_time.startswith(today_str))
        ]

        # 2. Fetch recurring tasks
        recurring_reminders = [
            r.to_dict() for r in all_reminders
            if r.recurrence.value != "none"
        ]

        # 3. Check pending agent tasks if available
        pending_tasks = []
        if self.agent_manager and hasattr(self.agent_manager, "list_tasks"):
            try:
                tasks = self.agent_manager.list_tasks(status="RUNNING")
                pending_tasks = [{"id": t.task_id, "goal": t.goal} for t in tasks]
            except Exception as e:
                logger.debug(f"Could not query agent tasks for briefing: {e}")

        # 4. Learning focus from profile or preferences
        learning_pref = self.db.get_preference("learning_topic")
        learning_focus = learning_pref.value if learning_pref else profile.custom_attributes.get("learning_focus")

        # 5. Synthesize plain text summary
        greeting = f"Good morning, {name}."
        lines = [greeting, "\nHere is your daily briefing:"]

        if today_reminders:
            lines.append(f"• {len(today_reminders)} scheduled reminder(s) today:")
            for r in today_reminders[:5]:
                t_str = r.get("next_trigger_at", "")[11:16] if r.get("next_trigger_at") else "Scheduled"
                lines.append(f"   - [{t_str}] {r.get('title')}")
        else:
            lines.append("• No specific reminders scheduled for today.")

        if recurring_reminders:
            lines.append(f"• {len(recurring_reminders)} recurring routine(s) active.")

        if pending_tasks:
            lines.append(f"• {len(pending_tasks)} pending background agent task(s).")

        if learning_focus:
            lines.append(f"• Planned learning focus: {learning_focus}.")

        lines.append("\nHave a focused and productive day.")
        synthesized = "\n".join(lines)

        briefing = BriefingData(
            date=today_str,
            greeting=greeting,
            reminders_today=today_reminders,
            recurring_tasks=recurring_reminders,
            pending_tasks=pending_tasks,
            learning_focus=learning_focus,
            notes=["Authentic local system briefing."],
            synthesized_text=synthesized
        )

        self.db.log_audit("morning_briefing_generated", {"date": today_str, "reminders_count": len(today_reminders)})
        return briefing

    def generate_evening_summary(self, user_name: Optional[str] = None) -> BriefingData:
        """
        Produce a grounded end-of-day summary.
        """
        profile = self.db.get_profile()
        name = user_name or (profile.preferred_address if profile.preferred_address else profile.preferred_name) or "there"
        today_str = date.today().isoformat()

        # Check completed reminders today
        all_rem = self.db.list_reminders()
        completed_today = [
            r.to_dict() for r in all_rem
            if r.status.value == "completed" and (
                (r.last_triggered_at and r.last_triggered_at.startswith(today_str))
                or (r.updated_at and r.updated_at.startswith(today_str))
                or (r.scheduled_time and r.scheduled_time.startswith(today_str))
            )
        ]
        pending_rem = [
            r.to_dict() for r in all_rem
            if r.enabled and r.status.value in ("pending", "snoozed")
        ]

        greeting = f"Good evening, {name}."
        lines = [greeting, "\nHere is your end-of-day summary:"]

        if completed_today:
            lines.append(f"• {len(completed_today)} reminder(s) completed today:")
            for r in completed_today[:5]:
                lines.append(f"   - {r.get('title')}")
        else:
            lines.append("• No completed reminders logged today.")

        if pending_rem:
            lines.append(f"• {len(pending_rem)} reminder(s) remaining for upcoming days.")
        else:
            lines.append("• All scheduled reminders are up to date.")

        lines.append("\nHave a restful evening.")
        synthesized = "\n".join(lines)

        summary = BriefingData(
            date=today_str,
            greeting=greeting,
            reminders_today=completed_today,
            recurring_tasks=[],
            pending_tasks=pending_rem,
            notes=["End of day reflection."],
            synthesized_text=synthesized
        )

        self.db.log_audit("evening_summary_generated", {"date": today_str, "completed_count": len(completed_today)})
        return summary
