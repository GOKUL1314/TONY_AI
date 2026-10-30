"""
Abstract Base Tool definition for TONY AI (Stage 5).
Every executable tool must inherit from BaseTool and define its metadata, schema, and execution logic.
"""
from abc import ABC, abstractmethod
import logging
from typing import Any

from tools.schemas import ToolDefinition, ToolExecutionResult, RiskLevel

logger = logging.getLogger("tony.tools.base")


class BaseTool(ABC):
    """Abstract Base Class for all registered TONY tools."""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the tool metadata and parameter schema."""
        pass

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate incoming parameters against the tool's parameter schema.
        Returns (is_valid, error_message).
        """
        schema = self.definition.parameters
        for param_name, param_spec in schema.items():
            if param_spec.required:
                if param_name not in parameters or parameters[param_name] is None:
                    return False, f"Missing required parameter: '{param_name}'"
                val = parameters[param_name]
                if isinstance(val, str) and not val.strip():
                    return False, f"Parameter '{param_name}' cannot be empty."

        return True, None

    @abstractmethod
    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        """
        Execute the tool action with validated parameters.
        Must return a structured ToolExecutionResult.
        """
        pass

    def success(self, message: str, data: dict[str, Any] | None = None) -> ToolExecutionResult:
        """Helper to create a successful execution result."""
        return ToolExecutionResult(
            success=True,
            tool=self.definition.name,
            message=message,
            data=data or {},
            requires_confirmation=False,
            risk_level=self.definition.risk_level.value
        )

    def failure(self, message: str, error_code: str = "EXECUTION_ERROR", data: dict[str, Any] | None = None) -> ToolExecutionResult:
        """Helper to create a failed execution result."""
        return ToolExecutionResult(
            success=False,
            tool=self.definition.name,
            message=message,
            data=data or {},
            requires_confirmation=False,
            error_code=error_code,
            risk_level=self.definition.risk_level.value
        )
