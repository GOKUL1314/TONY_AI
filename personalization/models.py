"""
Data Models for TONY AI Personalization and Proactive Intelligence Subsystem (Stage 12).
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional
import uuid


class ReminderStatus(str, Enum):
    """Lifecycle state of a reminder."""
    PENDING = "pending"
    COMPLETED = "completed"
    SNOOZED = "snoozed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    MISSED = "missed"


class RecurrenceType(str, Enum):
    """Pattern of repetition for reminders and routines."""
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    WEEKDAYS = "weekdays"
    MONTHLY = "monthly"
    CUSTOM = "custom"


@dataclass
class UserProfile:
    """Core structured profile of user preferences and style attributes."""
    preferred_name: str = "Tony Stark"
    response_style: str = "concise"
    response_length: str = "medium"
    preferred_language: str = "English"
    learning_style: str = "step_by_step"
    proactive_mode: bool = False
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    max_daily_notifications: int = 5
    timezone: str = "Asia/Kolkata"
    custom_attributes: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def user_name(self) -> str:
        return self.preferred_name

    @user_name.setter
    def user_name(self, value: str):
        self.preferred_name = value

    @property
    def preferred_address(self) -> str:
        return self.custom_attributes.get("preferred_address", "Boss")

    @preferred_address.setter
    def preferred_address(self, value: str):
        self.custom_attributes["preferred_address"] = value

    @property
    def role(self) -> str:
        return self.custom_attributes.get("role", "Creator / Lead Engineer")

    @role.setter
    def role(self, value: str):
        self.custom_attributes["role"] = value

    @property
    def communication_style(self) -> str:
        return self.response_style

    @communication_style.setter
    def communication_style(self, value: str):
        self.response_style = value

    @property
    def verbosity(self) -> str:
        return self.response_length

    @verbosity.setter
    def verbosity(self, value: str):
        self.response_length = value

    @property
    def tone(self) -> str:
        return self.custom_attributes.get("tone", "iron_man_witty")

    @tone.setter
    def tone(self, value: str):
        self.custom_attributes["tone"] = value

    @property
    def wake_word_preference(self) -> str:
        return self.custom_attributes.get("wake_word_preference", "hey tony")

    @wake_word_preference.setter
    def wake_word_preference(self, value: str):
        self.custom_attributes["wake_word_preference"] = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preferred_name": self.preferred_name,
            "user_name": self.user_name,
            "preferred_address": self.preferred_address,
            "role": self.role,
            "response_style": self.response_style,
            "communication_style": self.communication_style,
            "response_length": self.response_length,
            "verbosity": self.verbosity,
            "tone": self.tone,
            "wake_word_preference": self.wake_word_preference,
            "preferred_language": self.preferred_language,
            "learning_style": self.learning_style,
            "proactive_mode": self.proactive_mode,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
            "max_daily_notifications": self.max_daily_notifications,
            "timezone": self.timezone,
            "custom_attributes": self.custom_attributes,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        clean = dict(data)
        if "user_name" in clean and "preferred_name" not in clean:
            clean["preferred_name"] = clean["user_name"]
        if "communication_style" in clean and "response_style" not in clean:
            clean["response_style"] = clean["communication_style"]
        if "verbosity" in clean and "response_length" not in clean:
            clean["response_length"] = clean["verbosity"]

        known = {
            "preferred_name", "response_style", "response_length",
            "preferred_language", "learning_style", "proactive_mode",
            "quiet_hours_start", "quiet_hours_end", "max_daily_notifications",
            "timezone", "custom_attributes", "updated_at"
        }
        kwargs = {k: v for k, v in clean.items() if k in known}
        extras = {k: v for k, v in clean.items() if k not in known}
        customs = kwargs.get("custom_attributes", {}) or {}
        if isinstance(customs, dict):
            customs.update(extras)
        kwargs["custom_attributes"] = customs
        return cls(**kwargs)


@dataclass
class UserPreference:
    """Individual typed preference with origin tracking and confidence score."""
    key: str
    value: Any
    category: str = "general"
    source: str = "explicit_user"
    confidence: float = 1.0
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "source": self.source,
            "confidence": round(self.confidence, 2),
            "updated_at": self.updated_at
        }


@dataclass
class Reminder:
    """Scheduled task or alarm with optional recurrence and timezone alignment."""
    id: str
    title: str
    description: str = ""
    scheduled_time: str = ""
    recurrence: RecurrenceType = RecurrenceType.NONE
    recurrence_interval_days: Optional[int] = None
    timezone: str = "Asia/Kolkata"
    enabled: bool = True
    status: ReminderStatus = ReminderStatus.PENDING
    last_triggered_at: Optional[str] = None
    next_trigger_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "scheduled_time": self.scheduled_time,
            "recurrence": self.recurrence.value if isinstance(self.recurrence, RecurrenceType) else str(self.recurrence),
            "recurrence_interval_days": self.recurrence_interval_days,
            "timezone": self.timezone,
            "enabled": self.enabled,
            "status": self.status.value if isinstance(self.status, ReminderStatus) else str(self.status),
            "last_triggered_at": self.last_triggered_at,
            "next_trigger_at": self.next_trigger_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


@dataclass
class RoutineStep:
    """Discrete action item within a defined automated routine."""
    step_id: str
    action_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action_type": self.action_type,
            "parameters": self.parameters,
            "description": self.description
        }


@dataclass
class Routine:
    """Pre-defined automated workflow scheduled or triggered on demand."""
    id: str
    name: str
    description: str = ""
    steps: List[RoutineStep] = field(default_factory=list)
    schedule_time: Optional[str] = None
    recurrence: RecurrenceType = RecurrenceType.NONE
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "schedule_time": self.schedule_time,
            "recurrence": self.recurrence.value if isinstance(self.recurrence, RecurrenceType) else str(self.recurrence),
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


@dataclass
class Notification:
    """Recorded message or prompt delivered to the user through active channels."""
    id: str
    title: str
    message: str
    channel: str = "in_app"
    delivered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_read: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_type: str = "reminder"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "channel": self.channel,
            "delivered_at": self.delivered_at,
            "is_read": self.is_read,
            "metadata": self.metadata,
            "source_type": self.source_type
        }


@dataclass
class ProactiveSuggestion:
    """Contextually generated suggestion presented to the user for explicit approval."""
    id: str
    suggestion_type: str
    title: str
    description: str
    proposed_action: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    cooldown_until: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "suggestion_type": self.suggestion_type,
            "title": self.title,
            "description": self.description,
            "proposed_action": self.proposed_action,
            "status": self.status,
            "created_at": self.created_at,
            "cooldown_until": self.cooldown_until
        }


@dataclass
class BriefingData:
    """Structured contents of morning briefing or evening summary."""
    date: str
    greeting: str
    reminders_today: List[Dict[str, Any]] = field(default_factory=list)
    recurring_tasks: List[Dict[str, Any]] = field(default_factory=list)
    pending_tasks: List[Dict[str, Any]] = field(default_factory=list)
    learning_focus: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    synthesized_text: str = ""

    @property
    def spoken_text(self) -> str:
        return self.synthesized_text

    @spoken_text.setter
    def spoken_text(self, value: str):
        self.synthesized_text = value

    @property
    def text(self) -> str:
        return self.synthesized_text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "greeting": self.greeting,
            "reminders_today": self.reminders_today,
            "recurring_tasks": self.recurring_tasks,
            "pending_tasks": self.pending_tasks,
            "learning_focus": self.learning_focus,
            "notes": self.notes,
            "synthesized_text": self.synthesized_text,
            "spoken_text": self.spoken_text,
            "text": self.text
        }
