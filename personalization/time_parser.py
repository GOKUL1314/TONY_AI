"""
Natural Language Time and Schedule Parser for TONY AI Personalization Subsystem (Stage 12).
Parses relative intervals, explicit times, calendar dates, and recurrence expressions
into timezone-aware ISO 8601 timestamps and RecurrenceType enums.
"""
import re
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import Optional, Tuple, Dict, Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # fallback if needed

from personalization.models import RecurrenceType
from personalization.errors import TimeParsingError

logger = logging.getLogger("tony.personalization.time_parser")

WEEKDAYS_MAP = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6
}


@dataclass
class ParsedTimeResult:
    """Structured output of a natural language time parsing operation."""
    scheduled_time: datetime
    iso_string: str
    recurrence: RecurrenceType
    recurrence_interval_days: Optional[int] = None
    is_ambiguous: bool = False
    clarification_prompt: Optional[str] = None
    extracted_title: str = ""
    original_expression: str = ""

    @property
    def target_time(self) -> datetime:
        return self.scheduled_time


class NaturalLanguageTimeParser:
    """Parses user natural language scheduling queries into concrete timestamps."""

    def __init__(self, default_timezone: str = "Asia/Kolkata"):
        self.default_timezone = default_timezone

    def get_tz(self, tz_name: Optional[str] = None):
        """Retrieve ZoneInfo object or UTC fallback."""
        tz_str = tz_name or self.default_timezone
        try:
            return ZoneInfo(tz_str)
        except Exception:
            try:
                return ZoneInfo("UTC")
            except Exception:
                return None

    def parse(self, text: str, reference_time: Optional[datetime] = None) -> ParsedTimeResult:
        """
        Parse natural language reminder / schedule string.
        Extracts both time and remaining task title.
        """
        clean_text = text.strip()
        tz = self.get_tz()
        now = reference_time or (datetime.now(tz) if tz else datetime.now())

        recurrence = RecurrenceType.NONE
        interval_days = None
        target_dt = None
        extracted_title = clean_text
        is_ambiguous = False
        clarification = None

        lower = clean_text.lower()

        # -------------------------------------------------------------
        # 1. Recurrence Detection
        # -------------------------------------------------------------
        # "every weekday at X"
        if re.search(r"\bevery\s+weekday\b", lower):
            recurrence = RecurrenceType.WEEKDAYS
        # "every day at X" / "daily at X"
        elif re.search(r"\b(?:every\s+day|daily)\b", lower):
            recurrence = RecurrenceType.DAILY
        # "every [monday|tuesday|...]"
        elif (m_w := re.search(r"\bevery\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", lower)):
            recurrence = RecurrenceType.WEEKLY
        # "every month on the X" / "monthly"
        elif re.search(r"\b(?:every\s+month|monthly)\b", lower):
            recurrence = RecurrenceType.MONTHLY

        # -------------------------------------------------------------
        # 2. Relative Durations: "in X minutes/hours/days"
        # -------------------------------------------------------------
        rel_match = re.search(r"\bin\s+(\d+)\s*(mins?|minutes?|hours?|hrs?|days?|secs?|seconds?)\b", lower)
        if rel_match:
            qty = int(rel_match.group(1))
            unit = rel_match.group(2).lower()
            if "sec" in unit:
                target_dt = now + timedelta(seconds=qty)
            elif "min" in unit:
                target_dt = now + timedelta(minutes=qty)
            elif "hr" in unit or "hour" in unit:
                target_dt = now + timedelta(hours=qty)
            elif "day" in unit:
                target_dt = now + timedelta(days=qty)

        # -------------------------------------------------------------
        # 3. Tomorrow / Today with Time
        # -------------------------------------------------------------
        if target_dt is None:
            # Check tomorrow
            is_tomorrow = bool(re.search(r"\btomorrow\b", lower))
            is_today = bool(re.search(r"\b(?:today|tonight)\b", lower))
            base_date = now.date()
            if is_tomorrow:
                base_date = (now + timedelta(days=1)).date()

            # Check explicit time: "at 9 AM", "at 9:30 PM", "at 18:00", "9 AM", "10:30 PM"
            time_match = re.search(
                r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
                lower
            )

            # Check period indicators
            has_morning = "morning" in lower
            has_afternoon = "afternoon" in lower
            has_evening = "evening" in lower or "tonight" in lower

            if time_match and (time_match.group(3) or time_match.group(2) or "at " in lower or is_tomorrow or is_today):
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                meridiem = time_match.group(3)

                if meridiem:
                    if meridiem == "pm" and hour < 12:
                        hour += 12
                    elif meridiem == "am" and hour == 12:
                        hour = 0
                elif hour < 12:
                    if has_evening or "tonight" in lower:
                        hour += 12
                    elif has_afternoon and hour < 12:
                        hour += 12
                    elif not has_morning and hour <= 7:
                        # Ambiguous: e.g. "at 7" could be 7 AM or 7 PM
                        is_ambiguous = True
                        clarification = f"Did you mean {hour}:00 AM or {hour}:00 PM?"

                target_time = time(hour=min(23, hour), minute=min(59, minute))
                candidate_dt = datetime.combine(base_date, target_time)
                if tz:
                    candidate_dt = candidate_dt.replace(tzinfo=tz)

                # If time is earlier today and user said "at 9 AM" without "tomorrow", schedule next day
                if not is_tomorrow and candidate_dt <= now and recurrence == RecurrenceType.NONE:
                    candidate_dt += timedelta(days=1)

                target_dt = candidate_dt

            elif has_morning:
                target_dt = datetime.combine(base_date, time(9, 0))
                if tz: target_dt = target_dt.replace(tzinfo=tz)
                if target_dt <= now and not is_tomorrow: target_dt += timedelta(days=1)
            elif has_evening or "tonight" in lower:
                target_dt = datetime.combine(base_date, time(20, 0))
                if tz: target_dt = target_dt.replace(tzinfo=tz)
                if target_dt <= now and not is_tomorrow: target_dt += timedelta(days=1)

        # -------------------------------------------------------------
        # 4. Weekday specific: "every Monday at 9 AM" or "on Monday at 9 AM"
        # -------------------------------------------------------------
        if target_dt is None or recurrence in (RecurrenceType.WEEKLY, RecurrenceType.WEEKDAYS):
            m_day = re.search(r"\b(?:on\s+|every\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", lower)
            if m_day and target_dt is None:
                day_name = m_day.group(1).lower()
                target_weekday = WEEKDAYS_MAP.get(day_name, 0)
                days_ahead = (target_weekday - now.weekday()) % 7
                if days_ahead == 0 and recurrence == RecurrenceType.NONE:
                    days_ahead = 7
                base_date = (now + timedelta(days=days_ahead)).date()
                target_dt = datetime.combine(base_date, time(9, 0))
                if tz: target_dt = target_dt.replace(tzinfo=tz)

        # Fallback default: 1 hour from now if time could not be parsed
        if target_dt is None:
            target_dt = now + timedelta(hours=1)
            is_ambiguous = True
            clarification = "Could not detect an exact time; defaulting to 1 hour from now."

        # Ensure target_dt has timezone info
        if target_dt.tzinfo is None and tz is not None:
            target_dt = target_dt.replace(tzinfo=tz)

        # -------------------------------------------------------------
        # 5. Extract Reminder Title
        # -------------------------------------------------------------
        # Remove trigger prefixes like "remind me to", "remind me in 10 minutes to", "every day at 9 AM to"
        cleaned_title = re.sub(r"^(?:please\s+|tony[,!:]?\s*)*(?:remind\s+me(?:\s+to)?|schedule(?:\s+a)?\s+reminder(?:\s+to)?|create(?:\s+a)?\s+reminder(?:\s+to)?)\s*", "", clean_text, flags=re.IGNORECASE)
        # Strip time phrases
        cleaned_title = re.sub(r"\bin\s+\d+\s*(?:mins?|minutes?|hours?|hrs?|days?|secs?|seconds?)\b", "", cleaned_title, flags=re.IGNORECASE)
        cleaned_title = re.sub(r"\b(?:tomorrow|today|tonight|every\s+day|daily|every\s+weekday|every\s+\w+day)\b", "", cleaned_title, flags=re.IGNORECASE)
        cleaned_title = re.sub(r"\b(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", "", cleaned_title, flags=re.IGNORECASE)
        cleaned_title = re.sub(r"\b(?:in\s+the\s+)?(?:morning|afternoon|evening)\b", "", cleaned_title, flags=re.IGNORECASE)
        cleaned_title = re.sub(r"^(?:to\s+|that\s+)", "", cleaned_title.strip(), flags=re.IGNORECASE).strip()
        cleaned_title = re.sub(r"^[\s,.-]+|[\s,.-]+$", "", cleaned_title)

        if not cleaned_title:
            cleaned_title = clean_text

        return ParsedTimeResult(
            scheduled_time=target_dt,
            iso_string=target_dt.isoformat(),
            recurrence=recurrence,
            recurrence_interval_days=interval_days,
            is_ambiguous=is_ambiguous,
            clarification_prompt=clarification,
            extracted_title=cleaned_title,
            original_expression=clean_text
        )
