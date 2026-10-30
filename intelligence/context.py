"""
Conversational Context and Short-Term State Engine for TONY AI (Stage 8).
Maintains unified session state (active image, active video, active file, recent results)
and performs pronoun and reference resolution across multi-turn interactions.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

logger = logging.getLogger("tony.intelligence.context")


@dataclass
class ConversationContext:
    """Short-term conversational state separate from long-term SQLite memory."""
    conversation_id: str = "default_session"
    active_image_id: Optional[str] = None
    active_image_path: Optional[str] = None
    active_image_prompt: Optional[str] = None

    active_video_id: Optional[str] = None
    active_video_path: Optional[str] = None
    active_video_prompt: Optional[str] = None

    active_file_path: Optional[str] = None
    active_folder_path: Optional[str] = None

    last_tool_name: Optional[str] = None
    last_tool_result: Optional[Any] = None

    active_task_id: Optional[str] = None
    pending_confirmation: Optional[Dict[str, Any]] = None

    recent_messages: List[Dict[str, str]] = field(default_factory=list)
    max_recent_messages: int = 10

    def sync_with_subsystems(self, image_manager=None, video_manager=None) -> None:
        """Synchronize active media pointers with Stage 6 & Stage 7 managers."""
        if image_manager and hasattr(image_manager, "get_active_image"):
            active_img = image_manager.get_active_image()
            if active_img:
                self.active_image_id = active_img.image_id
                self.active_image_path = getattr(active_img, "file_path", None)
                self.active_image_prompt = getattr(active_img, "prompt", None)

        if video_manager and hasattr(video_manager, "get_active_video"):
            active_vid = video_manager.get_active_video()
            if active_vid:
                self.active_video_id = active_vid.video_id
                self.active_video_path = getattr(active_vid, "file_path", None)
                self.active_video_prompt = getattr(active_vid, "prompt", None)

    def set_active_image(self, image_id: str, path: Optional[str] = None, prompt: Optional[str] = None) -> None:
        self.active_image_id = image_id
        if path:
            self.active_image_path = path
        if prompt:
            self.active_image_prompt = prompt

    def set_active_video(self, video_id: str, path: Optional[str] = None, prompt: Optional[str] = None) -> None:
        self.active_video_id = video_id
        if path:
            self.active_video_path = path
        if prompt:
            self.active_video_prompt = prompt

    def set_active_file(self, path: str) -> None:
        self.active_file_path = path

    def set_active_folder(self, path: str) -> None:
        self.active_folder_path = path

    def add_message(self, role: str, content: str) -> None:
        self.recent_messages.append({"role": role, "content": content})
        if len(self.recent_messages) > self.max_recent_messages:
            self.recent_messages = self.recent_messages[-self.max_recent_messages:]

    def resolve_references(self, text: str) -> Dict[str, Any]:
        """
        Analyze user text for referential pronouns ("that image", "it", "the video we made", "that folder")
        and resolve them to active session context entities.
        """
        resolved: Dict[str, Any] = {}
        clean = text.strip().lower()

        # Image reference patterns
        image_ref_match = re.search(
            r"\b(?:that\s+image|the\s+image|this\s+image|the\s+picture|that\s+picture|this\s+picture|it\b)",
            clean
        )
        if image_ref_match and self.active_image_id:
            resolved["image_id"] = self.active_image_id
            resolved["image_path"] = self.active_image_path
            resolved["image_prompt"] = self.active_image_prompt

        # Video reference patterns
        video_ref_match = re.search(
            r"\b(?:that\s+video|the\s+video|this\s+video|the\s+clip|that\s+clip|the\s+animation|video\s+we\s+just\s+made)\b",
            clean
        )
        if video_ref_match and self.active_video_id:
            resolved["video_id"] = self.active_video_id
            resolved["video_path"] = self.active_video_path
            resolved["video_prompt"] = self.active_video_prompt

        # File reference patterns
        file_ref_match = re.search(
            r"\b(?:that\s+file|the\s+file|this\s+file|the\s+previous\s+file)\b",
            clean
        )
        if file_ref_match and self.active_file_path:
            resolved["file_path"] = self.active_file_path

        # Folder reference patterns
        folder_ref_match = re.search(
            r"\b(?:that\s+folder|the\s+folder|this\s+folder|that\s+directory|the\s+directory)\b",
            clean
        )
        if folder_ref_match and self.active_folder_path:
            resolved["folder_path"] = self.active_folder_path

        # General "open it" reference
        if re.search(r"^(?:open|launch)\s+it$", clean):
            if self.active_folder_path:
                resolved["target_to_open"] = self.active_folder_path
                resolved["target_type"] = "folder"
            elif self.active_file_path:
                resolved["target_to_open"] = self.active_file_path
                resolved["target_type"] = "file"

        return resolved

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "active_image_id": self.active_image_id,
            "active_image_prompt": self.active_image_prompt,
            "active_video_id": self.active_video_id,
            "active_video_prompt": self.active_video_prompt,
            "active_file_path": self.active_file_path,
            "active_folder_path": self.active_folder_path,
            "last_tool_name": self.last_tool_name,
            "active_task_id": self.active_task_id,
            "has_pending_confirmation": bool(self.pending_confirmation),
            "recent_messages_count": len(self.recent_messages)
        }
