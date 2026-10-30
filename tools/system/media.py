"""
Media playback control tools for TONY AI (Stage 5).
Uses standard Windows user32 multimedia virtual key events.
"""
import ctypes
import logging
import platform
from typing import Any

from tools.base import BaseTool
from tools.schemas import ToolDefinition, ToolExecutionResult, RiskLevel

logger = logging.getLogger("tony.tools.system.media")

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


def _send_media_key(vk_code: int) -> bool:
    """Send Windows virtual media key event."""
    if platform.system() != "Windows":
        logger.info(f"Simulating media key 0x{vk_code:X} on non-Windows OS.")
        return True

    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        logger.error(f"Failed to send media virtual key event 0x{vk_code:X}: {e}")
        return False


class MediaPlayPauseTool(BaseTool):
    """Toggle media play / pause."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="play_pause",
            description="Toggle media playback (play or pause current media).",
            category="system",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={},
            examples=["Pause music", "Resume playback", "Play music", "Play pause"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        success = _send_media_key(VK_MEDIA_PLAY_PAUSE)
        if success:
            return self.success("Toggled media play/pause.")
        return self.failure("Failed to toggle media play/pause.", error_code="MEDIA_ERROR")


class MediaNextTool(BaseTool):
    """Skip to next media track."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="next_track",
            description="Skip to the next media track.",
            category="system",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={},
            examples=["Next track", "Next song", "Skip song"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        success = _send_media_key(VK_MEDIA_NEXT_TRACK)
        if success:
            return self.success("Skipped to next track.")
        return self.failure("Failed to skip media track.", error_code="MEDIA_ERROR")


class MediaPrevTool(BaseTool):
    """Return to previous media track."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="previous_track",
            description="Return to the previous media track.",
            category="system",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={},
            examples=["Previous track", "Previous song", "Go back to last song"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        success = _send_media_key(VK_MEDIA_PREV_TRACK)
        if success:
            return self.success("Returned to previous track.")
        return self.failure("Failed to go to previous media track.", error_code="MEDIA_ERROR")
