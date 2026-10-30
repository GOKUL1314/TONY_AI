"""
Agent Lifecycle Manager for TONY AI Agent Subsystem (Stage 10).
Coordinates planning, validation, execution, state tracking, human confirmation,
pause/resume/cancel controls, and active task registry.
"""
import logging
import uuid
from typing import Dict, Any, List, Optional, Callable

from agent.models import (
    AgentTask,
    AgentPlan,
    AgentStep,
    AgentStepStatus,
    AgentTaskStatus,
    AgentRiskLevel
)
from agent.planner import AgentPlanner
from agent.executor import AgentExecutor
from agent.state import AgentState
from agent.errors import AgentExecutionError, AgentSecurityError
from intelligence.context import ConversationContext

logger = logging.getLogger("tony.agent.manager")


class AgentManager:
    """
    Central coordinator for Stage 10 agentic workflows.
    Bridges user commands to plans, manages execution state, and enforces controls.
    """

    def __init__(
        self,
        planner: Optional[AgentPlanner] = None,
        executor: Optional[AgentExecutor] = None,
        orchestrator = None
    ):
        self.planner = planner or AgentPlanner()
        self.executor = executor or AgentExecutor()
        self.orchestrator = orchestrator

        self.tasks: Dict[str, AgentTask] = {}
        self.states: Dict[str, AgentState] = {}  # conversation_id -> AgentState
        self.task_states: Dict[str, AgentState] = {}  # task_id -> AgentState

    def get_state(self, conversation_id: str = "default_session") -> AgentState:
        """Retrieve or create live AgentState for a conversation session."""
        if conversation_id not in self.states:
            state = AgentState(task_id="", conversation_id=conversation_id)
            if self.orchestrator:
                ctx = self.orchestrator.get_context(conversation_id)
                if ctx:
                    state.sync_from_context(ctx)
            self.states[conversation_id] = state
        return self.states[conversation_id]

    def execute(self, user_goal: str, conversation_id: str = "default_session") -> AgentTask:
        """
        Synthesize plan and begin execution for a given user goal.
        """
        if not user_goal or not isinstance(user_goal, str) or not user_goal.strip():
            raise AgentExecutionError("User goal must be a non-empty string.")

        clean_goal = user_goal.strip()
        state = self.get_state(conversation_id)

        # Sync context from orchestrator if available
        ctx = None
        if self.orchestrator:
            ctx = self.orchestrator.get_context(conversation_id)
            if ctx:
                state.sync_from_context(ctx)

        # 1. Synthesize Plan
        try:
            plan = self.planner.plan(clean_goal, context=ctx)
        except AgentSecurityError:
            raise
        except Exception as plan_err:
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            failed_plan = AgentPlan(
                plan_id=f"plan_{uuid.uuid4().hex[:8]}",
                user_goal=clean_goal,
                status=AgentTaskStatus.FAILED
            )
            task = AgentTask(
                task_id=task_id,
                user_goal=clean_goal,
                plan=failed_plan,
                conversation_id=conversation_id,
                status=AgentTaskStatus.FAILED,
                error=str(plan_err),
                natural_response=f"I couldn't plan this task: {str(plan_err)}"
            )
            self.tasks[task_id] = task
            self.task_states[task_id] = state
            return task

        # 2. Register Task
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        task = AgentTask(
            task_id=task_id,
            user_goal=clean_goal,
            plan=plan,
            conversation_id=conversation_id,
            status=AgentTaskStatus.QUEUED
        )
        state.task_id = task_id
        self.tasks[task_id] = task
        self.task_states[task_id] = state

        # 3. Execute Plan
        task = self.executor.execute_plan(task, state)

        # 4. Bidirectional Sync back to orchestrator session context
        if self.orchestrator and ctx:
            state.sync_to_context(ctx)

        return task

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        """Retrieve task by ID."""
        return self.tasks.get(task_id)

    def list_tasks(self, status: Optional[str] = None, limit: int = 50) -> List[AgentTask]:
        """List tasks, optionally filtered by status, newest first."""
        all_tasks = list(self.tasks.values())
        all_tasks.reverse()
        if status:
            stat_norm = status.lower()
            all_tasks = [
                t for t in all_tasks
                if (t.status.value if hasattr(t.status, "value") else str(t.status)).lower() == stat_norm
            ]
        return all_tasks[:limit]

    def list_active_tasks(self) -> List[AgentTask]:
        """List currently active, queued, waiting, or paused tasks."""
        active_statuses = {
            AgentTaskStatus.QUEUED,
            AgentTaskStatus.PLANNING,
            AgentTaskStatus.RUNNING,
            AgentTaskStatus.WAITING_CONFIRMATION,
            AgentTaskStatus.PAUSED
        }
        return [
            t for t in self.tasks.values()
            if t.status in active_statuses
        ]

    def confirm_task(self, task_id: str, confirmation_id: Optional[str] = None) -> AgentTask:
        """
        Approve a pending confirmation gate and continue execution.
        """
        task = self.get_task(task_id)
        if not task:
            raise AgentExecutionError(f"Task '{task_id}' not found.")

        state = self.task_states.get(task_id) or self.get_state(task.conversation_id)

        # Locate the step waiting for confirmation
        target_step = None
        for step in task.plan.steps:
            if step.status == AgentStepStatus.WAITING_CONFIRMATION:
                target_step = step
                break

        if not target_step:
            # Check if any step requires confirmation
            for step in task.plan.steps:
                if step.requires_confirmation:
                    target_step = step
                    break

        if not target_step:
            raise AgentExecutionError(f"Task '{task_id}' has no steps waiting for confirmation.")

        # Unlock step
        target_step.requires_confirmation = False
        target_step.status = AgentStepStatus.PENDING
        task.pending_confirmation_id = None
        state.pending_confirmation = None

        task.status = AgentTaskStatus.RUNNING
        task.plan.status = AgentTaskStatus.RUNNING
        self.executor.emit_event(task, "step_confirmed", target_step, f"Action confirmed: {target_step.description}")

        # Resume execution
        task = self.executor.execute_plan(task, state)

        if self.orchestrator:
            ctx = self.orchestrator.get_context(task.conversation_id)
            if ctx:
                state.sync_to_context(ctx)

        return task

    def cancel_task(self, task_id: str, reason: str = "User cancelled the task.") -> AgentTask:
        """
        Cancel a running, queued, or waiting task immediately.
        """
        task = self.get_task(task_id)
        if not task:
            raise AgentExecutionError(f"Task '{task_id}' not found.")

        state = self.task_states.get(task_id) or self.get_state(task.conversation_id)

        task.is_cancelled = True
        state.is_cancelled = True

        if task.status not in (AgentTaskStatus.COMPLETED, AgentTaskStatus.FAILED):
            task.status = AgentTaskStatus.CANCELLED
            task.plan.status = AgentTaskStatus.CANCELLED
            for step in task.plan.steps:
                if step.status in (AgentStepStatus.PENDING, AgentStepStatus.RUNNING, AgentStepStatus.WAITING_CONFIRMATION, AgentStepStatus.PAUSED):
                    step.status = AgentStepStatus.CANCELLED
            task.natural_response = "The task has been cancelled as requested."
            self.executor.emit_event(task, "task_cancelled", message=reason)

        return task

    def pause_task(self, task_id: str) -> AgentTask:
        """
        Pause an executing task.
        """
        task = self.get_task(task_id)
        if not task:
            raise AgentExecutionError(f"Task '{task_id}' not found.")

        state = self.task_states.get(task_id) or self.get_state(task.conversation_id)

        task.is_paused = True
        state.is_paused = True
        task.status = AgentTaskStatus.PAUSED
        task.plan.status = AgentTaskStatus.PAUSED
        task.natural_response = "The task is currently paused."
        self.executor.emit_event(task, "task_paused", message="Task paused by user.")
        return task

    def resume_task(self, task_id: str) -> AgentTask:
        """
        Resume a paused task.
        """
        task = self.get_task(task_id)
        if not task:
            raise AgentExecutionError(f"Task '{task_id}' not found.")

        if task.status != AgentTaskStatus.PAUSED and not task.is_paused:
            return task

        state = self.task_states.get(task_id) or self.get_state(task.conversation_id)

        task.is_paused = False
        state.is_paused = False

        # Reset any paused step to pending so it resumes
        for step in task.plan.steps:
            if step.status == AgentStepStatus.PAUSED:
                step.status = AgentStepStatus.PENDING

        task.status = AgentTaskStatus.RUNNING
        task.plan.status = AgentTaskStatus.RUNNING
        self.executor.emit_event(task, "task_resumed", message="Resuming task execution.")

        task = self.executor.execute_plan(task, state)

        if self.orchestrator:
            ctx = self.orchestrator.get_context(task.conversation_id)
            if ctx:
                state.sync_to_context(ctx)

        return task

    def retry_task(self, task_id: str) -> AgentTask:
        """
        Retry execution of a failed task from the point of failure.
        """
        task = self.get_task(task_id)
        if not task:
            raise AgentExecutionError(f"Task '{task_id}' not found.")

        if task.status != AgentTaskStatus.FAILED:
            return task

        state = self.task_states.get(task_id) or self.get_state(task.conversation_id)

        # Unblock and reset failed steps
        for step in task.plan.steps:
            if step.status in (AgentStepStatus.FAILED, AgentStepStatus.BLOCKED):
                step.status = AgentStepStatus.PENDING
                step.error = None
                step.retry_count = 0

        task.status = AgentTaskStatus.RUNNING
        task.plan.status = AgentTaskStatus.RUNNING
        task.error = None
        self.executor.emit_event(task, "task_retrying", message="Retrying failed task.")

        task = self.executor.execute_plan(task, state)
        return task

    def add_listener(self, task_id: str, listener: Callable) -> None:
        """Register a progress callback for a task."""
        self.executor.add_listener(task_id, listener)

    def remove_listener(self, task_id: str, listener: Callable) -> None:
        """Unregister a progress callback for a task."""
        self.executor.remove_listener(task_id, listener)
