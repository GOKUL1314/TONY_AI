"""
TONY AI Personalization and Proactive Intelligence Subsystem (Stage 12).
Provides structured user profile management, granular preferences, scheduled reminders,
recurring tasks, morning briefings, quiet hours, and contextual prompt adaptation.
"""
from personalization.models import (
    UserProfile,
    UserPreference,
    Reminder,
    ReminderStatus,
    RecurrenceType,
    Routine,
    RoutineStep,
    Notification,
    BriefingData,
    ProactiveSuggestion
)
from personalization.storage import PersonalizationDatabase
from personalization.profile import ProfileManager
from personalization.preferences import PreferencesManager
from personalization.time_parser import NaturalLanguageTimeParser, ParsedTimeResult
from personalization.policy import PersonalizationPolicy
from personalization.notifications import (
    BaseNotificationProvider,
    InAppNotificationProvider,
    VoiceNotificationProvider,
    NotificationService
)
from personalization.scheduler import AutomationScheduler
from personalization.briefing import BriefingGenerator
from personalization.routines import RoutineManager
from personalization.context import PersonalizationContextBuilder
from personalization.manager import PersonalizationManager
from personalization.errors import (
    PersonalizationError,
    ProfileValidationError,
    PreferenceNotFoundError,
    ReminderNotFoundError,
    RoutineNotFoundError,
    SchedulerError,
    RateLimitExceededError,
    QuietHoursError,
    ConsequentialActionBlockedError,
    TimeParsingError
)

__all__ = [
    "PersonalizationManager",
    "UserProfile",
    "UserPreference",
    "Reminder",
    "ReminderStatus",
    "RecurrenceType",
    "Routine",
    "RoutineStep",
    "Notification",
    "BriefingData",
    "ProactiveSuggestion",
    "PersonalizationDatabase",
    "ProfileManager",
    "PreferencesManager",
    "NaturalLanguageTimeParser",
    "ParsedTimeResult",
    "PersonalizationPolicy",
    "BaseNotificationProvider",
    "InAppNotificationProvider",
    "VoiceNotificationProvider",
    "NotificationService",
    "AutomationScheduler",
    "BriefingGenerator",
    "RoutineManager",
    "PersonalizationContextBuilder",
    "PersonalizationError",
    "ProfileValidationError",
    "PreferenceNotFoundError",
    "ReminderNotFoundError",
    "RoutineNotFoundError",
    "SchedulerError",
    "RateLimitExceededError",
    "QuietHoursError",
    "ConsequentialActionBlockedError",
    "TimeParsingError"
]
