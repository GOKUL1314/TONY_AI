"""
Confirmation management engine for TONY AI (Stage 5).
Tracks, validates, and manages pending destructive/high-risk tool actions awaiting user authorization.
"""
import logging
import time
import uuid
from typing import Any

from tools.schemas import PendingAction, RiskLevel

logger = logging.getLogger("tony.tools.confirmation")


class ConfirmationManager:
    """In-memory coordinator for pending tool confirmations with timeouts."""

    def __init__(self, default_timeout: int = 60):
        self.default_timeout = default_timeout
        self._pending: dict[str, PendingAction] = {}

    def create_pending(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        description: str,
        risk_level: RiskLevel = RiskLevel.HIGH,
        timeout_seconds: int | None = None
    ) -> PendingAction:
        """Create and register a new pending action requiring user confirmation."""
        self.clean_expired()
        action_id = f"act_{uuid.uuid4().hex[:8]}"
        timeout = timeout_seconds or self.default_timeout
        expires_at = time.time() + timeout

        pending = PendingAction(
            id=action_id,
            tool_name=tool_name,
            parameters=parameters,
            risk_level=risk_level,
            description=description,
            created_at=time.time(),
            expires_at=expires_at
        )

        self._pending[action_id] = pending
        logger.info(f"Created pending confirmation #{action_id} for tool '{tool_name}' (expires in {timeout}s)")
        return pending

    def get_pending(self, confirmation_id: str) -> PendingAction | None:
        """Fetch pending action by ID if it has not expired and not consumed."""
        self.clean_expired()
        action = self._pending.get(confirmation_id)
        if action and not action.is_expired() and not getattr(action, "consumed", False):
            return action
        return None

    def get_active_pending(self) -> PendingAction | None:
        """
        Get the most recent valid pending action.
        Useful for natural chat/voice confirmation (e.g. user says 'Yes Tony' or clicks [CONFIRM]).
        """
        self.clean_expired()
        valid = [a for a in self._pending.values() if not a.is_expired() and not getattr(a, "consumed", False)]
        if not valid:
            return None
        # Return most recently created
        return max(valid, key=lambda a: a.created_at)

    def validate_token(
        self,
        token: str,
        tool_name: str,
        parameters: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """
        Validate that a confirmation token exists, is unexpired, unconsumed,
        and strictly matches the specified tool_name and arguments.
        Returns (is_valid, error_message).
        """
        self.clean_expired()
        action = self._pending.get(token)
        if not action:
            return False, "Confirmation token is invalid, expired, or has already been used."
        if action.is_expired():
            self._pending.pop(token, None)
            return False, "Confirmation token has expired."
        if getattr(action, "consumed", False):
            return False, "Confirmation token has already been consumed and cannot be reused."

        if action.tool_name.lower().strip() != tool_name.lower().strip():
            return False, f"Confirmation token was issued for '{action.tool_name}', not '{tool_name}'."

        # Strictly check target/name parameter arguments
        act_params = {k: v for k, v in action.parameters.items() if k != "confirmation_token"}
        req_params = {k: v for k, v in parameters.items() if k != "confirmation_token"}

        act_target = str(act_params.get("target") or act_params.get("name") or "").replace("\\", "/").strip().lower()
        req_target = str(req_params.get("target") or req_params.get("name") or "").replace("\\", "/").strip().lower()
        if act_target and req_target and act_target != req_target:
            if not (act_target.endswith(req_target) or req_target.endswith(act_target)):
                return False, f"Confirmation token arguments mismatch: expected target '{act_target}', got '{req_target}'."

        return True, None

    def consume_token(
        self,
        token: str,
        tool_name: str,
        parameters: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Validate and immediately consume the token so it cannot be reused."""
        is_valid, err = self.validate_token(token, tool_name, parameters)
        if not is_valid:
            return False, err

        action = self._pending.pop(token, None)
        if action:
            action.consumed = True
            logger.info(f"Consumed confirmation token #{token} for tool '{tool_name}'")
            return True, None
        return False, "Failed to consume token."

    def confirm(self, confirmation_id: str) -> PendingAction | None:
        """Validate and pop the pending action for execution."""
        self.clean_expired()
        action = self._pending.pop(confirmation_id, None)
        if action and not action.is_expired() and not getattr(action, "consumed", False):
            action.consumed = True
            logger.info(f"User explicitly CONFIRMED action #{confirmation_id} [{action.tool_name}]")
            return action
        return None

    def cancel(self, confirmation_id: str) -> bool:
        """Cancel and remove a pending action."""
        action = self._pending.pop(confirmation_id, None)
        if action:
            action.consumed = True
            logger.info(f"User explicitly CANCELLED action #{confirmation_id} [{action.tool_name}]")
            return True
        return False

    def cancel_all(self) -> int:
        """Cancel and remove all pending actions."""
        count = len(self._pending)
        for act in self._pending.values():
            act.consumed = True
        self._pending.clear()
        return count

    def list_pending(self) -> list[PendingAction]:
        """Return all non-expired pending actions."""
        self.clean_expired()
        return [a for a in self._pending.values() if not a.is_expired() and not getattr(a, "consumed", False)]

    def clean_expired(self) -> int:
        """Purge all expired or consumed pending actions."""
        expired_ids = [aid for aid, act in self._pending.items() if act.is_expired() or getattr(act, "consumed", False)]
        for aid in expired_ids:
            self._pending.pop(aid, None)
            logger.debug(f"Purged expired/consumed pending action #{aid}")
        return len(expired_ids)
