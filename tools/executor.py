"""
Tool Execution engine for TONY AI (Stage 5).
Coordinates tool validation, permission checks, confirmation workflows,
and execution logging.
"""
from collections import deque
from datetime import datetime
import logging
from typing import Any

from tools.confirmation import ConfirmationManager
from tools.permissions import PermissionManager
from tools.registry import ToolRegistry
from tools.schemas import RiskLevel, ToolExecutionResult, PendingAction

logger = logging.getLogger("tony.tools.executor")


class ToolExecutor:
    """Safely executes authorized tools, enforces confirmation for high-risk operations, and maintains activity telemetry."""

    def __init__(
        self,
        registry: ToolRegistry,
        confirmation_manager: ConfirmationManager | None = None,
        max_activity_log: int = 50
    ):
        self.registry = registry
        self.confirmation_manager = confirmation_manager or ConfirmationManager()
        self._activity_log: deque[dict[str, Any]] = deque(maxlen=max_activity_log)

        # Wire confirmation_manager into all tools in registry that support it
        for tname in self.registry.get_tool_names():
            t = self.registry.get_tool(tname)
            if hasattr(t, "confirmation_manager") and getattr(t, "confirmation_manager") is None:
                t.confirmation_manager = self.confirmation_manager

    def execute_plan(
        self,
        plan: dict[str, Any],
        skip_confirmation: bool = False,
        confirmation_token: str | None = None
    ) -> ToolExecutionResult:
        """
        Execute a planned tool action with full permission and risk verification.
        Enforces that HIGH-risk destructive tools must have a valid, unexpired confirmation token
        matching the exact tool and arguments.
        """
        tool_name = str(plan.get("tool", "")).strip().lower()
        parameters = dict(plan.get("parameters", {}) or {})

        # 1. Verify tool registration
        if not self.registry.is_registered(tool_name):
            logger.warning(f"Rejected execution: Unknown tool '{tool_name}'")
            return self._record_result(ToolExecutionResult(
                success=False,
                tool=tool_name,
                message=f"Tool '{tool_name}' is not recognized or registered.",
                error_code="UNKNOWN_TOOL"
            ))

        tool = self.registry.get_tool(tool_name)

        # 2. Schema parameter validation
        is_valid, val_err = tool.validate_parameters(parameters)
        if not is_valid:
            logger.warning(f"Parameter validation failed for '{tool_name}': {val_err}")
            return self._record_result(ToolExecutionResult(
                success=False,
                tool=tool_name,
                message=val_err or "Invalid parameters.",
                error_code="INVALID_PARAMETERS"
            ))

        # 3. Assess Action Risk Level
        risk_level = PermissionManager.evaluate_risk(tool_name, parameters)

        # 4. Critical operations blocked outright
        if risk_level == RiskLevel.CRITICAL:
            logger.critical(f"Security Alert: Critical operation blocked on '{tool_name}' with params {parameters}")
            return self._record_result(ToolExecutionResult(
                success=False,
                tool=tool_name,
                message="Security Policy Refusal: This action is classified as CRITICAL and is prohibited from automatic execution.",
                error_code="CRITICAL_OPERATION_BLOCKED",
                risk_level="critical"
            ))

        # 5. Check if action requires user confirmation (High risk or explicitly flagged)
        needs_confirm = (risk_level == RiskLevel.HIGH or tool.definition.requires_confirmation)
        token = confirmation_token or plan.get("confirmation_token") or parameters.get("confirmation_token")

        if needs_confirm:
            # A HIGH-risk tool must refuse to run unless a valid, unexpired confirmation token exists
            if not token:
                target_desc = parameters.get("target") or parameters.get("name") or tool_name
                desc = f"Permanently delete or alter '{target_desc}'"
                pending = self.confirmation_manager.create_pending(
                    tool_name=tool_name,
                    parameters=parameters,
                    description=desc,
                    risk_level=risk_level
                )

                prompt_msg = (
                    f"⚠️ Confirmation Required: That action will permanently modify or delete '{target_desc}'. "
                    f"Do you want me to continue?"
                )

                return self._record_result(ToolExecutionResult(
                    success=False,
                    tool=tool_name,
                    message=prompt_msg,
                    requires_confirmation=True,
                    confirmation_id=pending.id,
                    risk_level=risk_level.value,
                    data={"pending_action": pending.to_dict()}
                ))

            # A token WAS provided: strictly validate for this exact action and arguments
            is_valid_tok, val_msg = self.confirmation_manager.validate_token(token, tool_name, parameters)
            if not is_valid_tok:
                logger.warning(f"Refused execution for '{tool_name}' with invalid token '{token}': {val_msg}")
                return self._record_result(ToolExecutionResult(
                    success=False,
                    tool=tool_name,
                    message=f"Confirmation rejected: {val_msg}",
                    error_code="INVALID_CONFIRMATION_TOKEN",
                    risk_level=risk_level.value
                ))

            # Valid token: consume it so it cannot be reused
            self.confirmation_manager.consume_token(token, tool_name, parameters)
            parameters["confirmation_token"] = token

        # 6. Execute safe or authorized tool
        try:
            logger.info(f"Executing tool '{tool_name}' [Risk: {risk_level.value}]")
            result = tool.execute(parameters)
            result.risk_level = risk_level.value
            return self._record_result(result)
        except Exception as e:
            logger.exception(f"Unexpected exception executing tool '{tool_name}': {e}")
            return self._record_result(ToolExecutionResult(
                success=False,
                tool=tool_name,
                message=f"An error occurred while executing {tool_name}: {str(e)}",
                error_code="INTERNAL_TOOL_ERROR",
                risk_level=risk_level.value
            ))

    def confirm_action(self, confirmation_id: str) -> ToolExecutionResult:
        """Authorize and execute a pending high-risk action."""
        pending = self.confirmation_manager.get_pending(confirmation_id)
        if not pending or pending.is_expired() or getattr(pending, "consumed", False):
            return ToolExecutionResult(
                success=False,
                tool="confirmation",
                message="Confirmation ID is invalid, expired, or has already been used.",
                error_code="INVALID_CONFIRMATION_ID"
            )

        logger.info(f"Executing confirmed action #{confirmation_id}: '{pending.tool_name}'")
        params = dict(pending.parameters)
        params["confirmation_token"] = confirmation_id
        return self.execute_plan(
            {"tool": pending.tool_name, "parameters": params},
            confirmation_token=confirmation_id
        )

    def cancel_action(self, confirmation_id: str) -> ToolExecutionResult:
        """Cancel a pending high-risk action."""
        success = self.confirmation_manager.cancel(confirmation_id)
        if success:
            return ToolExecutionResult(
                success=True,
                tool="confirmation",
                message="Action cancelled. No changes were made."
            )
        return ToolExecutionResult(
            success=False,
            tool="confirmation",
            message="No active pending action found matching that ID.",
            error_code="CONFIRMATION_NOT_FOUND"
        )

    def get_activity_log(self) -> list[dict[str, Any]]:
        """Return chronological activity log of recent tool actions."""
        return list(self._activity_log)

    def _record_result(self, result: ToolExecutionResult) -> ToolExecutionResult:
        """Record outcome in the telemetry ring buffer."""
        status_str = "SUCCESS" if result.success else ("CONFIRMATION_REQUIRED" if result.requires_confirmation else "FAILED")
        self._activity_log.append({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "tool": result.tool,
            "status": status_str,
            "message": result.message,
            "risk_level": result.risk_level
        })
        return result
