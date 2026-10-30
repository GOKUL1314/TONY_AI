"""
Data Models for TONY AI Intelligence Subsystem (Stage 8).
Defines structured classes for Intent, TaskPlan, TaskStep, ExecutionProgress, and Status enums.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional
import uuid


class IntentType(str, Enum):
    """Enumeration of recognized user intentions."""
    CHAT = "CHAT"
    QUESTION = "QUESTION"
    MEMORY_SAVE = "MEMORY_SAVE"
    MEMORY_RECALL = "MEMORY_RECALL"
    MEMORY_FORGET = "MEMORY_FORGET"
    MEMORY_CLEAR = "MEMORY_CLEAR"
    WINDOWS_ACTION = "WINDOWS_ACTION"
    IMAGE_GENERATION = "IMAGE_GENERATION"
    IMAGE_EDIT = "IMAGE_EDIT"
    IMAGE_REGENERATE = "IMAGE_REGENERATE"
    VIDEO_GENERATION = "VIDEO_GENERATION"
    IMAGE_TO_VIDEO = "IMAGE_TO_VIDEO"
    VISION_ANALYZE = "VISION_ANALYZE"
    VISION_QUESTION = "VISION_QUESTION"
    VISION_OCR = "VISION_OCR"
    VISION_DESCRIBE = "VISION_DESCRIBE"
    FILE_OPERATION = "FILE_OPERATION"
    MULTI_STEP_TASK = "MULTI_STEP_TASK"
    SYSTEM_INFORMATION = "SYSTEM_INFORMATION"
    CANCEL_TASK = "CANCEL_TASK"
    PERSONAL_PROFILE = "PERSONAL_PROFILE"
    PREFERENCE_SET = "PREFERENCE_SET"
    PREFERENCE_GET = "PREFERENCE_GET"
    PROACTIVE_ENABLE = "PROACTIVE_ENABLE"
    PROACTIVE_DISABLE = "PROACTIVE_DISABLE"
    PROACTIVE_STATUS = "PROACTIVE_STATUS"
    REMINDER_CREATE = "REMINDER_CREATE"
    REMINDER_LIST = "REMINDER_LIST"
    REMINDER_UPDATE = "REMINDER_UPDATE"
    REMINDER_DELETE = "REMINDER_DELETE"
    REMINDER_SNOOZE = "REMINDER_SNOOZE"
    RECURRING_TASK_CREATE = "RECURRING_TASK_CREATE"
    RECURRING_TASK_CANCEL = "RECURRING_TASK_CANCEL"
    DAILY_BRIEFING = "DAILY_BRIEFING"
    EVENING_SUMMARY = "EVENING_SUMMARY"
    ROUTINE_CREATE = "ROUTINE_CREATE"
    ROUTINE_RUN = "ROUTINE_RUN"
    ROUTINE_DISABLE = "ROUTINE_DISABLE"
    PERSONALIZED_SUGGESTION = "PERSONALIZED_SUGGESTION"
    KNOWLEDGE_SEARCH = "KNOWLEDGE_SEARCH"
    KNOWLEDGE_QUERY = "KNOWLEDGE_QUERY"
    KNOWLEDGE_INGEST = "KNOWLEDGE_INGEST"
    PROACTIVE_CONTROL = "PROACTIVE_CONTROL"
    SELF_UPGRADE = "SELF_UPGRADE"
    SELF_DIAGNOSTIC = "SELF_DIAGNOSTIC"
    SELF_TEST = "SELF_TEST"
    SELF_STATUS = "SELF_STATUS"
    SELF_ANALYZE = "SELF_ANALYZE"
    SELF_UPGRADE_PLAN = "SELF_UPGRADE_PLAN"
    SELF_UPGRADE_APPLY = "SELF_UPGRADE_APPLY"
    SELF_ROLLBACK = "SELF_ROLLBACK"
    HELP = "HELP"
    UNKNOWN = "UNKNOWN"



@dataclass
class Intent:
    """Structured internal representation of classified user intention."""
    type: IntentType
    confidence: float = 1.0
    user_request: str = ""
    entities: Dict[str, Any] = field(default_factory=dict)
    required_tools: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    requires_clarification: bool = False
    clarification_prompt: Optional[str] = None
    sub_intents: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value if isinstance(self.type, IntentType) else str(self.type),
            "confidence": self.confidence,
            "user_request": self.user_request,
            "entities": self.entities,
            "required_tools": self.required_tools,
            "requires_confirmation": self.requires_confirmation,
            "requires_clarification": self.requires_clarification,
            "clarification_prompt": self.clarification_prompt,
            "sub_intents": self.sub_intents
        }


class TaskStatus(str, Enum):
    """Lifecycle statuses for a TaskPlan."""
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    """Lifecycle statuses for an individual TaskStep."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"


@dataclass
class TaskStep:
    """A single atomic, validated step within a TaskPlan."""
    step_id: str
    action_type: str
    description: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    requires_confirmation: bool = False
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retries: int = 0

    def to_dict(self) -> Dict[str, Any]:
        res_data = self.result
        if hasattr(res_data, "to_dict"):
            res_data = res_data.to_dict()
        return {
            "step_id": self.step_id,
            "action_type": self.action_type,
            "description": self.description,
            "arguments": self.arguments,
            "dependencies": self.dependencies,
            "status": self.status.value if isinstance(self.status, StepStatus) else str(self.status),
            "result": res_data,
            "error": self.error,
            "requires_confirmation": self.requires_confirmation,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retries": self.retries
        }


@dataclass
class TaskPlan:
    """A complete structured execution plan consisting of one or more steps."""
    task_id: str
    original_request: str
    created_at: str
    status: TaskStatus = TaskStatus.QUEUED
    steps: List[TaskStep] = field(default_factory=list)
    current_step_index: int = 0
    result: Optional[Any] = None
    error: Optional[str] = None
    requires_confirmation: bool = False
    pending_confirmation_id: Optional[str] = None
    natural_response: Optional[str] = None
    is_cancelled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        res_data = self.result
        if hasattr(res_data, "to_dict"):
            res_data = res_data.to_dict()
        return {
            "task_id": self.task_id,
            "original_request": self.original_request,
            "created_at": self.created_at,
            "status": self.status.value if isinstance(self.status, TaskStatus) else str(self.status),
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "result": res_data,
            "error": self.error,
            "requires_confirmation": self.requires_confirmation,
            "pending_confirmation_id": self.pending_confirmation_id,
            "natural_response": self.natural_response,
            "is_cancelled": self.is_cancelled
        }

    @classmethod
    def create(cls, request: str, steps: Optional[List[TaskStep]] = None) -> "TaskPlan":
        now = datetime.now()
        task_id = f"task_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        return cls(
            task_id=task_id,
            original_request=request,
            created_at=now.isoformat(),
            status=TaskStatus.QUEUED,
            steps=steps or []
        )


@dataclass
class ExecutionProgress:
    """Progress event emitted during task execution."""
    task_id: str
    step_id: Optional[str]
    step_index: int
    total_steps: int
    status: str
    message: str
    percent: Optional[int] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
