"""
Plan and Input Validator for TONY AI Agent Subsystem (Stage 10).
Validates user input, checks for prompt injection, verifies DAG dependencies,
and resolves dynamic parameter interpolation ($step_X.result...).
"""
import re
import logging
from typing import Dict, Any, List, Optional
from agent.models import AgentPlan, AgentStep, AgentStepStatus
from agent.errors import AgentSecurityError, AgentPlanError
from tools.permissions import PermissionManager
from memory.extractor import is_sensitive_secret

logger = logging.getLogger("tony.agent.validator")

# Prompt injection detection patterns
INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior|your)?\s*(?:instructions|rules|security|protocols|safety)\b"),
    re.compile(r"(?i)\brun\s+(?:powershell|cmd|bash|shell|terminal)\b"),
    re.compile(r"(?i)\bformat\s+[a-z]:\b"),
    re.compile(r"(?i)\bdelete\s+(?:all|everything|c:\\|c:/)\b"),
    re.compile(r"(?i)\bbypass\s+(?:security|controls|sandbox|confirmation)\b"),
]


class AgentValidator:
    """Validates inputs, plans, and step arguments before execution."""

    @classmethod
    def validate_user_request(cls, text: str) -> None:
        """Scan user prompt for prompt injection and malicious commands."""
        if not text or not text.strip():
            raise AgentSecurityError("User goal cannot be empty.")

        for pattern in INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning(f"Prompt injection pattern detected in user goal: '{text}'")
                raise AgentSecurityError(
                    "Security Alert: Your request contains patterns that violate system safety policies."
                )

        if is_sensitive_secret(text):
            logger.warning(f"Sensitive secret or credential detected in user request: '{text}'")
            raise AgentSecurityError(
                "Security Alert: Your request contains sensitive credentials, passwords, or API keys."
            )

    @classmethod
    def validate_plan(cls, plan: AgentPlan) -> None:
        """Verify plan structure, step ID uniqueness, and dependency consistency."""
        step_ids = set()
        for idx, step in enumerate(plan.steps):
            if step.step_id in step_ids:
                raise AgentPlanError(f"Duplicate step ID '{step.step_id}' in plan.")
            step_ids.add(step.step_id)

            # Dependencies must precede the current step
            preceding_ids = {s.step_id for s in plan.steps[:idx]}
            for dep in step.dependencies:
                if dep not in preceding_ids:
                    raise AgentPlanError(
                        f"Step '{step.step_id}' has invalid or forward dependency '{dep}'."
                    )

    @classmethod
    def resolve_step_arguments(
        cls,
        step: AgentStep,
        plan: AgentPlan
    ) -> Dict[str, Any]:
        """
        Resolve dynamic argument templates like '$step_1.result.image_id' or '$step_1.result.path'.
        Ensures values are strictly grounded in real execution outputs without hallucination.
        """
        resolved: Dict[str, Any] = {}
        completed_map = {s.step_id: s for s in plan.steps if s.status == AgentStepStatus.COMPLETED}

        for key, val in step.arguments.items():
            if isinstance(val, str) and val.startswith("$step_"):
                # Format: $step_X.result.property or $step_X.result
                parts = val[1:].split(".")
                dep_id = parts[0]
                dep_step = completed_map.get(dep_id)

                if not dep_step or dep_step.result is None:
                    raise AgentPlanError(
                        f"Step '{step.step_id}' references missing result from '{dep_id}'."
                    )

                curr_val = dep_step.result
                for sub_prop in parts[1:]:
                    if sub_prop == "result":
                        continue
                    if isinstance(curr_val, dict):
                        curr_val = curr_val.get(sub_prop)
                    elif hasattr(curr_val, sub_prop):
                        curr_val = getattr(curr_val, sub_prop)
                    else:
                        raise AgentPlanError(
                            f"Step '{step.step_id}' cannot resolve property '{sub_prop}' from '{dep_id}' result."
                        )

                resolved[key] = curr_val
            else:
                resolved[key] = val

        return resolved
