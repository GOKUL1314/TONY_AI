"""
Tool schemas, definitions, risk levels, and execution results for TONY (Stage 5).
"""
from dataclasses import dataclass, field, asdict
from enum import Enum
import time
from typing import Any


class RiskLevel(str, Enum):
    """Permission and safety risk levels for system tools."""
    LOW = "low"           # Safe, non-destructive read or minor operation (no confirmation)
    MEDIUM = "medium"     # File copy/move, application close (confirmation if sensitive)
    HIGH = "high"         # Destructive operation: delete file/folder, bulk delete (always requires confirmation)
    CRITICAL = "critical" # System modification (format, registry, firewall, system32) -> REFUSED


@dataclass
class ToolParameter:
    """Specification of a parameter accepted by a tool."""
    name: str
    type: str = "string"  # 'string', 'integer', 'boolean', 'list'
    description: str = ""
    required: bool = True
    default: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "required": self.required,
            "default": self.default
        }


@dataclass
class ToolDefinition:
    """Complete metadata and parameter definition for a registered tool."""
    name: str
    description: str
    category: str  # 'system', 'filesystem', 'browser', 'utilities'
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    parameters: dict[str, ToolParameter] = field(default_factory=dict)
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, RiskLevel) else str(self.risk_level),
            "requires_confirmation": self.requires_confirmation,
            "parameters": {k: v.to_dict() for k, v in self.parameters.items()},
            "examples": self.examples
        }


@dataclass
class ToolExecutionResult:
    """Predictable result returned after executing a tool or requesting confirmation."""
    success: bool
    tool: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_id: str | None = None
    error_code: str | None = None
    risk_level: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "tool": self.tool,
            "message": self.message,
            "data": self.data,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_id": self.confirmation_id,
            "error_code": self.error_code,
            "risk_level": self.risk_level
        }


@dataclass
class PendingAction:
    """A high-risk action queued for explicit user confirmation before execution."""
    id: str
    tool_name: str
    parameters: dict[str, Any]
    risk_level: RiskLevel
    description: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    consumed: bool = False

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, RiskLevel) else str(self.risk_level),
            "description": self.description,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "is_expired": self.is_expired(),
            "consumed": self.consumed
        }
