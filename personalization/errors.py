"""
Typed Exceptions for TONY AI Personalization and Proactive Intelligence Subsystem (Stage 12).
"""


class PersonalizationError(Exception):
    """Base exception for all personalization errors."""
    pass


class ProfileValidationError(PersonalizationError):
    """Raised when profile validation fails or forbidden fields are supplied."""
    pass


class PreferenceNotFoundError(PersonalizationError):
    """Raised when a requested user preference is not found."""
    pass


class ReminderNotFoundError(PersonalizationError):
    """Raised when a reminder by ID is not found."""
    pass


class RoutineNotFoundError(PersonalizationError):
    """Raised when a routine by ID is not found."""
    pass


class SchedulerError(PersonalizationError):
    """Raised when scheduler operations fail or scheduler thread encounters fatal state."""
    pass


class RateLimitExceededError(PersonalizationError):
    """Raised when proactive notification quota for the day is exhausted."""
    pass


class QuietHoursError(PersonalizationError):
    """Raised when a proactive notification or routine is blocked due to active quiet hours."""
    pass


class ConsequentialActionBlockedError(PersonalizationError):
    """Raised when an autonomous action is blocked by consequential action safety policies."""
    pass


class TimeParsingError(PersonalizationError):
    """Raised when natural language time expression cannot be resolved unambiguously."""
    pass
