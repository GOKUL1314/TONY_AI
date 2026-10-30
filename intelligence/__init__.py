"""
TONY AI Intelligence Subsystem.
Unifies chat, voice, memory, automation tools, image synthesis, video generation,
and self-upgrade into a single, coherent JARVIS-style desktop assistant.
"""
from intelligence.models import (
    Intent,
    IntentType,
    TaskPlan,
    TaskStep,
    TaskStatus,
    StepStatus,
    ExecutionProgress
)
from intelligence.context import ConversationContext
from intelligence.intent import IntentEngine
from intelligence.planner import TaskPlanner
from intelligence.confirmations import OrchestrationConfirmationManager
from intelligence.responses import NaturalResponseEngine
from intelligence.orchestrator import TonyOrchestrator
from intelligence.system_prompt import build_system_prompt, TONY_BASE_SYSTEM_PROMPT
from intelligence.capabilities import CapabilityRegistry, CapabilityStatus
from intelligence.model_router import ModelRouter, TaskCategory, RouteTarget
from intelligence.evaluator import SelfEvaluator, EvaluationResult
from intelligence.recovery import ErrorRecoveryManager, FailureType, FailureAnalysis
from intelligence.pipeline import IntelligencePipeline, PipelineResult
from intelligence.errors import (
    IntelligenceError,
    IntentError,
    PlanningError,
    DependencyError,
    OrchestrationError,
    StepExecutionError,
    SecurityRejectionError,
    sanitize_message
)

__all__ = [
    "TonyOrchestrator",
    "IntentEngine",
    "Intent",
    "IntentType",
    "TaskPlanner",
    "TaskPlan",
    "TaskStep",
    "TaskStatus",
    "StepStatus",
    "ExecutionProgress",
    "ConversationContext",
    "OrchestrationConfirmationManager",
    "NaturalResponseEngine",
    "build_system_prompt",
    "TONY_BASE_SYSTEM_PROMPT",
    "CapabilityRegistry",
    "CapabilityStatus",
    "ModelRouter",
    "TaskCategory",
    "RouteTarget",
    "SelfEvaluator",
    "EvaluationResult",
    "ErrorRecoveryManager",
    "FailureType",
    "FailureAnalysis",
    "IntelligencePipeline",
    "PipelineResult",
    "IntelligenceError",
    "IntentError",
    "PlanningError",
    "DependencyError",
    "OrchestrationError",
    "StepExecutionError",
    "SecurityRejectionError",
    "sanitize_message"
]
