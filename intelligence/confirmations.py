"""
Confirmation Management for TONY AI Task Orchestration (Stage 8).
Enforces security gating on HIGH-risk task steps (folder/file deletion, sensitive operations),
ensuring explicit user authorization before execution proceeds.
"""
import logging
import time
from typing import Optional, Dict, Any, Tuple
from intelligence.models import TaskPlan, TaskStep, TaskStatus, StepStatus

logger = logging.getLogger("tony.intelligence.confirmations")

CONFIRM_TOKENS = {
    "yes", "y", "confirm", "proceed", "do it", "sure", "ok", "okay",
    "go ahead", "yes please", "yeah", "yep", "affirmative", "execute", "continue"
}

CANCEL_TOKENS = {
    "no", "n", "cancel", "stop", "abort", "don't", "dont",
    "never mind", "nevermind", "no don't", "negative", "cancel it"
}


class OrchestrationConfirmationManager:
    """Tracks and validates pending user confirmations for high-risk task plans."""

    def __init__(self, timeout_seconds: int = 60):
        self.timeout_seconds = timeout_seconds
        self._pending: Dict[str, Dict[str, Any]] = {}

    def request_confirmation(self, plan: TaskPlan, step_index: int) -> str:
        """
        Record a pending confirmation gate for a specific task and step.
        Returns the confirmation prompt for the user.
        """
        step = plan.steps[step_index]
        step.status = StepStatus.WAITING_CONFIRMATION
        plan.status = TaskStatus.WAITING_CONFIRMATION
        plan.current_step_index = step_index

        conf_id = f"conf_{plan.task_id}_{step.step_id}"
        plan.pending_confirmation_id = conf_id

        tool_name = step.arguments.get("tool", step.action_type)
        desc = step.description or f"Execution of '{tool_name}'"

        self._pending[plan.task_id] = {
            "conf_id": conf_id,
            "task_id": plan.task_id,
            "step_index": step_index,
            "description": desc,
            "plan": plan,
            "created_at": time.time(),
            "expires_at": time.time() + self.timeout_seconds
        }

        logger.info(f"Confirmation requested for Task '{plan.task_id}' Step '{step.step_id}': {desc}")
        prompt = (
            f"Action authorization required: {desc}. "
            f"Do you want me to proceed? (Reply 'yes' or 'confirm' to execute, 'no' to cancel)"
        )
        return prompt

    def get_pending(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve active pending confirmation if not expired."""
        entry = self._pending.get(task_id)
        if not entry:
            return None
        if time.time() > entry["expires_at"]:
            logger.info(f"Confirmation for Task '{task_id}' has expired.")
            self._pending.pop(task_id, None)
            return None
        return entry

    def get_any_active(self) -> Optional[Dict[str, Any]]:
        """Get the most recent unexpired pending confirmation across all tasks."""
        now = time.time()
        active = [e for e in self._pending.values() if e["expires_at"] > now]
        if not active:
            return None
        active.sort(key=lambda x: x["created_at"], reverse=True)
        return active[0]

    def resolve_confirmation(self, task_id: str, approved: bool) -> Tuple[bool, Optional[TaskPlan], int]:
        """
        Resolve a pending confirmation.
        Returns (success, plan, step_index).
        """
        entry = self.get_pending(task_id)
        if not entry:
            return False, None, 0

        self._pending.pop(task_id, None)
        plan: TaskPlan = entry["plan"]
        step_idx: int = entry["step_index"]

        if approved:
            logger.info(f"Confirmation APPROVED for Task '{task_id}' Step index {step_idx}.")
            return True, plan, step_idx
        else:
            logger.info(f"Confirmation REJECTED for Task '{task_id}' Step index {step_idx}.")
            plan.status = TaskStatus.CANCELLED
            plan.steps[step_idx].status = StepStatus.CANCELLED
            plan.steps[step_idx].error = "Operation cancelled by user."
            return True, plan, step_idx

    @staticmethod
    def is_confirm_token(text: str) -> bool:
        clean = text.strip().lower().rstrip(".!?,")
        return clean in CONFIRM_TOKENS

    @staticmethod
    def is_cancel_token(text: str) -> bool:
        clean = text.strip().lower().rstrip(".!?,")
        return clean in CANCEL_TOKENS
