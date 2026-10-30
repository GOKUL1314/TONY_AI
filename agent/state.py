"""
State Management for TONY AI Agent Subsystem (Stage 10).
Maintains live in-memory operational state, tracking active media pointers,
completed/pending step indices, and session context synchronization.
"""
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class AgentState:
    """Operational runtime state for an active agent task."""
    task_id: str
    conversation_id: str = "default_session"
    current_step_id: Optional[str] = None
    current_step_index: int = 0
    completed_steps: List[str] = field(default_factory=list)
    failed_steps: List[str] = field(default_factory=list)
    pending_steps: List[str] = field(default_factory=list)
    blocked_steps: List[str] = field(default_factory=list)

    active_image_id: Optional[str] = None
    active_image_path: Optional[str] = None
    active_video_id: Optional[str] = None
    active_video_path: Optional[str] = None
    active_file_path: Optional[str] = None
    active_folder_path: Optional[str] = None

    last_tool: Optional[str] = None
    last_result: Optional[Any] = None
    pending_confirmation: Optional[Dict[str, Any]] = None

    retry_count: int = 0
    is_paused: bool = False
    is_cancelled: bool = False
    started_at: float = field(default_factory=time.time)

    @property
    def elapsed_seconds(self) -> float:
        return round(time.time() - self.started_at, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "conversation_id": self.conversation_id,
            "current_step_id": self.current_step_id,
            "current_step_index": self.current_step_index,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "pending_steps": self.pending_steps,
            "blocked_steps": self.blocked_steps,
            "active_image_id": self.active_image_id,
            "active_image_path": self.active_image_path,
            "active_video_id": self.active_video_id,
            "active_video_path": self.active_video_path,
            "active_file_path": self.active_file_path,
            "active_folder_path": self.active_folder_path,
            "last_tool": self.last_tool,
            "last_result": self.last_result,
            "pending_confirmation": self.pending_confirmation,
            "retry_count": self.retry_count,
            "is_paused": self.is_paused,
            "is_cancelled": self.is_cancelled,
            "elapsed_seconds": self.elapsed_seconds
        }

    def sync_to_context(self, ctx) -> None:
        """Sync agent state into Stage 8 ConversationContext."""
        if not ctx:
            return
        if self.active_image_id:
            ctx.set_active_image(self.active_image_id, path=self.active_image_path)
        if self.active_video_id:
            ctx.set_active_video(self.active_video_id, path=self.active_video_path)
        if self.active_folder_path:
            ctx.set_active_folder(self.active_folder_path)
        if self.active_file_path:
            ctx.set_active_file(self.active_file_path)
        if self.last_tool:
            ctx.last_tool_name = self.last_tool
            ctx.last_tool_result = self.last_result

    def sync_from_context(self, ctx) -> None:
        """Sync initial state from Stage 8 ConversationContext."""
        if not ctx:
            return
        self.active_image_id = ctx.active_image_id or self.active_image_id
        self.active_image_path = ctx.active_image_path or self.active_image_path
        self.active_video_id = ctx.active_video_id or self.active_video_id
        self.active_video_path = ctx.active_video_path or self.active_video_path
        self.active_folder_path = ctx.active_folder_path or self.active_folder_path
        self.active_file_path = ctx.active_file_path or self.active_file_path
        self.last_tool = ctx.last_tool_name or self.last_tool
        self.last_result = ctx.last_tool_result or self.last_result
