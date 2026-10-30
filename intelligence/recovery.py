"""
Error Recovery and Fault Classification Engine for TONY AI.
Classifies system, provider, and execution failures and guides safe retries (max 2)
with transparent, JARVIS-style failure explanations.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, Callable, TypeVar, Tuple
import logging
import time

logger = logging.getLogger("tony.intelligence.recovery")

T = TypeVar("T")


class FailureType(str, Enum):
    """Structured categories of operational and execution errors."""
    TRANSIENT = "TRANSIENT"
    TIMEOUT = "TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    QUOTA = "QUOTA"
    INVALID_INPUT = "INVALID_INPUT"
    AUTHENTICATION = "AUTHENTICATION"
    PERMISSION = "PERMISSION"
    SAFETY_BLOCK = "SAFETY_BLOCK"
    USER_CONFIRMATION_REQUIRED = "USER_CONFIRMATION_REQUIRED"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    UNKNOWN = "UNKNOWN"


@dataclass
class FailureAnalysis:
    """Detailed diagnosis of an error."""
    failure_type: FailureType
    original_error: str
    can_retry: bool
    recommended_action: str
    user_explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_type": self.failure_type.value,
            "original_error": self.original_error,
            "can_retry": self.can_retry,
            "recommended_action": self.recommended_action,
            "user_explanation": self.user_explanation
        }


class ErrorRecoveryManager:
    """Coordinates error analysis, retry loops (max 2 retries), and graceful degradation."""

    MAX_RETRIES = 2

    @classmethod
    def classify_error(cls, error: Exception, context: Optional[str] = None) -> FailureAnalysis:
        """Categorize an exception into typed FailureAnalysis."""
        err_str = str(error).lower()
        err_type_name = type(error).__name__.lower()

        # 1. Safety Block
        if "security" in err_str or "safety" in err_str or "injection" in err_str or "prohibited" in err_str:
            return FailureAnalysis(
                failure_type=FailureType.SAFETY_BLOCK,
                original_error=str(error),
                can_retry=False,
                recommended_action="Abort operation. Do not bypass security policy.",
                user_explanation="I couldn't complete that action because it violates system safety policy, Sir."
            )

        # 2. Confirmation Required
        if "confirmation" in err_str or "authorization required" in err_str:
            return FailureAnalysis(
                failure_type=FailureType.USER_CONFIRMATION_REQUIRED,
                original_error=str(error),
                can_retry=False,
                recommended_action="Wait for explicit user confirmation.",
                user_explanation="That requires your explicit confirmation before I can proceed, Sir."
            )

        # 3. Timeout
        if "timeout" in err_str or "timed out" in err_str or "timeouterror" in err_type_name:
            return FailureAnalysis(
                failure_type=FailureType.TIMEOUT,
                original_error=str(error),
                can_retry=True,
                recommended_action="Retry with exponential backoff up to 2 times.",
                user_explanation="I couldn't complete that because the provider timed out, Sir."
            )

        # 4. Authentication / API Key
        if "401" in err_str or "403" in err_str or "unauthorized" in err_str or "api key" in err_str or "token" in err_str:
            return FailureAnalysis(
                failure_type=FailureType.AUTHENTICATION,
                original_error=str(error),
                can_retry=False,
                recommended_action="Inspect API credentials in .env.",
                user_explanation="Authentication with the provider failed, Sir. Please check your configured credentials."
            )

        # 5. Quota / Rate Limit
        if "429" in err_str or "quota" in err_str or "rate limit" in err_str:
            return FailureAnalysis(
                failure_type=FailureType.QUOTA,
                original_error=str(error),
                can_retry=False,
                recommended_action="Pause requests or wait for quota reset.",
                user_explanation="The provider's rate or quota limit has been exceeded, Sir."
            )

        # 6. Provider Unavailable / Connection refused
        if "connection refused" in err_str or "cannot connect" in err_str or "503" in err_str or "502" in err_str:
            return FailureAnalysis(
                failure_type=FailureType.PROVIDER_UNAVAILABLE,
                original_error=str(error),
                can_retry=True,
                recommended_action="Verify local service or retry once.",
                user_explanation="The underlying provider service is currently unavailable, Sir."
            )

        # 7. Missing Dependency / Not Found
        if "modulenotfound" in err_type_name or "no such file" in err_str or "not found" in err_str:
            return FailureAnalysis(
                failure_type=FailureType.MISSING_DEPENDENCY,
                original_error=str(error),
                can_retry=False,
                recommended_action="Check prerequisite installations or file paths.",
                user_explanation="I couldn't locate a required dependency or file for this action, Sir."
            )

        # 8. Permission Denied
        if "permission" in err_str or "access is denied" in err_str or "permissionerror" in err_type_name:
            return FailureAnalysis(
                failure_type=FailureType.PERMISSION,
                original_error=str(error),
                can_retry=False,
                recommended_action="Check OS filesystem permissions.",
                user_explanation="Access was denied by the operating system, Sir."
            )

        # 9. Invalid Input
        if "valueerror" in err_type_name or "invalid" in err_str or "bad request" in err_str:
            return FailureAnalysis(
                failure_type=FailureType.INVALID_INPUT,
                original_error=str(error),
                can_retry=False,
                recommended_action="Provide sanitized, valid input arguments.",
                user_explanation="The input parameters provided were invalid, Sir."
            )

        # Default: Unknown / Transient
        return FailureAnalysis(
            failure_type=FailureType.UNKNOWN,
            original_error=str(error),
            can_retry=True,
            recommended_action="Retry once or notify user.",
            user_explanation=f"I couldn't complete that operation due to an unexpected issue ({error}), Sir."
        )

    @classmethod
    def execute_with_recovery(
        cls,
        operation: Callable[[], T],
        max_retries: int = 2,
        context_name: str = "operation"
    ) -> Tuple[bool, Optional[T], Optional[FailureAnalysis]]:
        """
        Executes an operation with safe retries (maximum 2 retries) based on failure type.
        Returns: (success: bool, result: Optional[T], analysis: Optional[FailureAnalysis])
        """
        effective_max_retries = min(max_retries, cls.MAX_RETRIES)
        last_error = None

        for attempt in range(effective_max_retries + 1):
            try:
                result = operation()
                return True, result, None
            except Exception as e:
                last_error = e
                analysis = cls.classify_error(e, context=context_name)
                logger.warning(
                    f"[{context_name}] Attempt {attempt + 1}/{effective_max_retries + 1} failed: "
                    f"Type={analysis.failure_type.value}, Error={e}"
                )

                if not analysis.can_retry or attempt == effective_max_retries:
                    return False, None, analysis

                # Sleep briefly before retry
                time.sleep(0.5 * (attempt + 1))

        fallback_analysis = cls.classify_error(last_error or Exception("Unknown error"))
        return False, None, fallback_analysis

    classify_failure = classify_error
