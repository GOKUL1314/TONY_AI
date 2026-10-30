"""
Structured Exceptions and Error Sanitization for TONY AI Intelligence Subsystem (Stage 8).
Ensures all errors are typed, descriptive, and strictly sanitized against secret leakage.
"""
from typing import Optional


class IntelligenceError(Exception):
    """Base exception for all Stage 8 Intelligence and Orchestration errors."""
    def __init__(self, message: str, code: str = "INTELLIGENCE_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code

    def __str__(self):
        return self.message


class IntentError(IntelligenceError):
    """Raised when intent detection fails or encounters malformed input."""
    def __init__(self, message: str):
        super().__init__(message, code="INTENT_ERROR")


class PlanningError(IntelligenceError):
    """Raised when a task plan cannot be constructed, has circular dependencies, or is invalid."""
    def __init__(self, message: str):
        super().__init__(message, code="PLANNING_ERROR")


class DependencyError(PlanningError):
    """Raised when a step depends on an unsatisfied or missing prior step output."""
    def __init__(self, message: str):
        super().__init__(message)
        self.code = "DEPENDENCY_ERROR"


class OrchestrationError(IntelligenceError):
    """Raised during plan execution or service dispatch failures."""
    def __init__(self, message: str, step_id: Optional[str] = None):
        super().__init__(message, code="ORCHESTRATION_ERROR")
        self.step_id = step_id


class StepExecutionError(OrchestrationError):
    """Raised when an individual task step fails during execution."""
    def __init__(self, message: str, step_id: str, action_type: str):
        super().__init__(f"Step '{step_id}' ({action_type}) failed: {message}", step_id=step_id)
        self.action_type = action_type


class SecurityRejectionError(IntelligenceError):
    """Raised when an action or plan attempts unauthorized execution or security policy breach."""
    def __init__(self, message: str):
        super().__init__(message, code="SECURITY_REJECTION")


def sanitize_message(text: str, secrets: Optional[list] = None) -> str:
    """
    Remove any sensitive tokens, API keys, or private credential strings from text.
    """
    if not text:
        return ""
    sanitized = text
    import re

    # Default secret patterns
    patterns = [
        re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{8,}", re.IGNORECASE),
        re.compile(r"sk-[a-zA-Z0-9]{15,}", re.IGNORECASE),
        re.compile(r"hf_[a-zA-Z0-9]{15,}", re.IGNORECASE),
        re.compile(r"ghp_[a-zA-Z0-9]{15,}", re.IGNORECASE),
    ]
    for pat in patterns:
        sanitized = pat.sub("[REDACTED_SECRET]", sanitized)

    if secrets:
        for s in secrets:
            if s and isinstance(s, str) and len(s) >= 4:
                sanitized = sanitized.replace(s, "[REDACTED_SECRET]")

    return sanitized
