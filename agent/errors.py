"""
Exception Classes for TONY AI Agent Subsystem (Stage 10).
"""


class AgentError(Exception):
    """Base exception for all agent operations."""
    pass


class AgentSecurityError(AgentError):
    """Raised when an action violates agent safety policies or contains prompt injection."""
    pass


class AgentPolicyViolationError(AgentSecurityError):
    """Raised when an operation is prohibited by policy (e.g. shell execution, credential access)."""
    pass


class AgentPlanError(AgentError):
    """Raised when multi-step plan generation or dependency validation fails."""
    pass


class AgentExecutionError(AgentError):
    """Raised when step execution fails."""
    def __init__(self, message: str, step_id: str, action: str):
        super().__init__(message)
        self.step_id = step_id
        self.action = action


class AgentRecoveryError(AgentError):
    """Raised when error recovery attempts are exhausted or unavailable."""
    pass


class AgentStateError(AgentError):
    """Raised when an invalid task state transition is attempted (e.g. resuming a completed task)."""
    pass
