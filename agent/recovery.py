"""
Failure Classification and Safe Recovery Engine for TONY AI Agent Subsystem (Stage 10).
Handles diagnostic categorization, limited transient retry, dependency cascading,
and safe self-correction without false success claims or silent fallbacks.
"""
import logging
from typing import Optional, List
from agent.models import (
    AgentStep,
    AgentPlan,
    AgentStepStatus,
    AgentFailure,
    AgentRiskLevel
)

logger = logging.getLogger("tony.agent.recovery")

# Keywords for failure classification
TRANSIENT_KEYWORDS = ["timeout", "connection reset", "temporarily unavailable", "try again", "timed out", "econnreset"]
QUOTA_KEYWORDS = ["quota", "rate limit", "too many requests", "429", "insufficient credits"]
UNAVAILABLE_KEYWORDS = ["connection refused", "not found in your local ollama library", "could not connect", "unreachable", "service unavailable", "503"]
SECURITY_KEYWORDS = ["security violation", "prompt injection", "unauthorized", "prohibited", "forbidden", "403", "401", "permission denied", "access denied", "restricted"]
ALREADY_EXISTS_KEYWORDS = ["already exists", "folder already exists", "file already exists", "already present"]


class FailureRecoveryManager:
    """Diagnoses step failures and coordinates safe, bounded recovery strategies."""

    MAX_RETRIES = 2

    @classmethod
    def classify_failure(cls, error_msg: str, step: AgentStep) -> AgentFailure:
        """Classify failure cause into structured diagnostic category."""
        clean_err = (error_msg or "").lower()

        # 1. State Already Exists (Self-correcting)
        if any(kw in clean_err for kw in ALREADY_EXISTS_KEYWORDS):
            return AgentFailure(
                failure_type="already_exists",
                recoverable=True,
                retry_count=step.retry_count,
                max_retries=0,
                error_message=error_msg
            )

        # 2. Security Violations (Fatal, no retries)
        if any(kw in clean_err for kw in SECURITY_KEYWORDS) or step.risk_level == AgentRiskLevel.CRITICAL:
            return AgentFailure(
                failure_type="permission_security",
                recoverable=False,
                retry_count=step.retry_count,
                max_retries=0,
                error_message=error_msg
            )

        # 3. Quota / Rate Limits (No automated retries, no silent paid fallback)
        if any(kw in clean_err for kw in QUOTA_KEYWORDS):
            return AgentFailure(
                failure_type="quota_limit",
                recoverable=False,
                retry_count=step.retry_count,
                max_retries=0,
                error_message=error_msg
            )

        # 4. Provider Unavailable
        if any(kw in clean_err for kw in UNAVAILABLE_KEYWORDS):
            return AgentFailure(
                failure_type="provider_unavailable",
                recoverable=False,
                retry_count=step.retry_count,
                max_retries=0,
                error_message=error_msg
            )

        # 5. Missing Dependency
        if "missing result" in clean_err or "cannot resolve property" in clean_err:
            return AgentFailure(
                failure_type="missing_dependency",
                recoverable=False,
                retry_count=step.retry_count,
                max_retries=0,
                error_message=error_msg
            )

        # 6. Transient Network / Server Glitches
        # Destructive or HIGH-risk actions are NEVER retried automatically!
        if any(kw in clean_err for kw in TRANSIENT_KEYWORDS) and step.risk_level != AgentRiskLevel.HIGH:
            can_retry = step.retry_count < cls.MAX_RETRIES
            return AgentFailure(
                failure_type="transient",
                recoverable=can_retry,
                retry_count=step.retry_count,
                max_retries=cls.MAX_RETRIES,
                error_message=error_msg
            )

        # 7. Default Unknown Error
        return AgentFailure(
            failure_type="unknown",
            recoverable=False,
            retry_count=step.retry_count,
            max_retries=0,
            error_message=error_msg
        )

    @classmethod
    def can_self_correct_existing_state(cls, failure: AgentFailure, step: AgentStep) -> bool:
        """
        Check if failure indicates the desired system state already exists
        (e.g., folder or file already created).
        """
        if failure.failure_type == "already_exists":
            if step.action_type in ("create_folder", "create_file"):
                return True
            if step.action_type == "tool_execution" and step.arguments.get("tool") in ("create_folder", "create_file"):
                return True
        return False

    @classmethod
    def block_downstream_dependencies(cls, failed_step_id: str, plan: AgentPlan) -> List[str]:
        """
        Cascading failure protection:
        Marks any step depending on failed_step_id (directly or transitively) as BLOCKED.
        """
        blocked_ids = []
        to_check = {failed_step_id}

        for step in plan.steps:
            if step.status == AgentStepStatus.PENDING:
                # Direct or transitive dependency check
                if any(dep in to_check for dep in step.dependencies):
                    step.status = AgentStepStatus.BLOCKED
                    step.error = f"Blocked: Preceding dependency '{failed_step_id}' failed."
                    to_check.add(step.step_id)
                    blocked_ids.append(step.step_id)

        if blocked_ids:
            logger.warning(
                f"Blocked {len(blocked_ids)} downstream steps due to failure in '{failed_step_id}': {blocked_ids}"
            )
        return blocked_ids
