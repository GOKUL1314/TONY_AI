"""
Policy Engine for Personalization and Proactive Intelligence (Stage 12).
Enforces quiet hours, daily rate limits, cooldown periods, prompt injection sanitization,
and consequential action safeguards.
"""
import re
import logging
from datetime import datetime, time, date
from typing import Tuple, Dict, Any, Optional

from personalization.models import UserProfile
from personalization.errors import RateLimitExceededError, QuietHoursError, ConsequentialActionBlockedError
from memory.extractor import is_sensitive_secret

logger = logging.getLogger("tony.personalization.policy")

# Actions that must NEVER be executed autonomously by proactive systems
CONSEQUENTIAL_ACTIONS = {
    "send_email", "send_message", "make_purchase", "delete_file",
    "delete_folder", "format_disk", "modify_registry", "execute_command",
    "powershell_command", "shell_execute", "transfer_funds", "publish_post"
}

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior|your)?\s*(?:instructions|rules|security|protocols|safety)\b"),
    re.compile(r"(?i)\brun\s+(?:powershell|cmd|bash|shell|terminal)\b"),
    re.compile(r"(?i)\bformat\s+[a-z]:\b"),
    re.compile(r"(?i)\bdelete\s+(?:all|everything|c:\\|c:/)\b"),
    re.compile(r"(?i)\bbypass\s+(?:security|controls|sandbox|confirmation)\b"),
    re.compile(r"(?i)\byou\s+are\s+now\s+(?:unrestricted|dan|jailbreak)\b")
]


class PersonalizationPolicy:
    """Enforces boundaries and rules for proactive assistant behaviors."""

    @classmethod
    def is_quiet_hours(cls, current_time: datetime, quiet_start: str = "22:00", quiet_end: str = "07:00") -> bool:
        """
        Check if the current time falls within configured quiet hours.
        Accurately handles overnight wrap-around (e.g., 22:00 to 07:00).
        """
        try:
            start_parts = [int(p) for p in quiet_start.split(":")]
            end_parts = [int(p) for p in quiet_end.split(":")]
            t_start = time(start_parts[0], start_parts[1])
            t_end = time(end_parts[0], end_parts[1])
        except Exception:
            t_start = time(22, 0)
            t_end = time(7, 0)

        cur_t = current_time.time()

        if t_start <= t_end:
            # Daytime range (e.g. 13:00 to 15:00)
            return t_start <= cur_t < t_end
        else:
            # Overnight range (e.g. 22:00 to 07:00)
            return cur_t >= t_start or cur_t < t_end

    @classmethod
    def can_send_proactive_notification(
        cls,
        profile: UserProfile,
        notifications_sent_today: int,
        current_time: Optional[datetime] = None,
        is_user_reminder: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate if a proactive notification can be dispatched.
        User-scheduled reminders are not blocked by proactive mode toggle,
        but unsolicited suggestions must obey proactive_mode, quiet hours, and daily limits.
        """
        now = current_time or datetime.now()

        # 1. Quiet hours check
        if cls.is_quiet_hours(now, profile.quiet_hours_start, profile.quiet_hours_end):
            # User-requested reminders may alert unless user explicitly silences all
            if not is_user_reminder:
                return False, f"Quiet hours active ({profile.quiet_hours_start} to {profile.quiet_hours_end})."

        # 2. Proactive mode check for unsolicited items
        if not is_user_reminder and not profile.proactive_mode:
            return False, "Proactive mode is currently disabled."

        # 3. Rate limit check
        if notifications_sent_today >= profile.max_daily_notifications:
            return False, f"Daily notification limit ({profile.max_daily_notifications}) reached."

        return True, None

    @classmethod
    def check_consequential_action(cls, action_type: str, arguments: Optional[Dict[str, Any]] = None) -> None:
        """
        Block autonomous execution of dangerous actions with real-world consequences.
        Raises ConsequentialActionBlockedError if violation detected.
        """
        action_clean = action_type.strip().lower()
        if action_clean in CONSEQUENTIAL_ACTIONS:
            raise ConsequentialActionBlockedError(
                f"Autonomous execution of consequential action '{action_type}' is strictly prohibited. "
                "Explicit user confirmation is mandatory."
            )

        args = arguments or {}
        tool_name = args.get("tool", "").lower()
        if tool_name in CONSEQUENTIAL_ACTIONS or tool_name.startswith("delete_"):
            raise ConsequentialActionBlockedError(
                f"Autonomous execution of tool '{tool_name}' requires explicit user confirmation."
            )

    @classmethod
    def sanitize_passive_text(cls, text: str, field_name: str = "reminder") -> str:
        """
        Sanitize reminder descriptions or titles.
        Neutralizes prompt injections and secret credentials so text is purely passive data.
        """
        if is_sensitive_secret(text):
            raise PersonalizationError(f"Sensitive credential detected in {field_name}. Storing secrets is prohibited.")

        for pat in PROMPT_INJECTION_PATTERNS:
            if pat.search(text):
                logger.warning(f"Prompt injection pattern detected and neutralized in {field_name}: '{text}'")
                text = pat.sub("[PROMPT_OVERRIDE_NEUTRALIZED]", text)

        return text.strip()
