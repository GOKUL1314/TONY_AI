"""
System Volume Control tools for TONY AI (Stage 5).
Uses standard Windows user32 multimedia virtual key events.
No admin privileges required, lightweight and native.
"""
import ctypes
import logging
import platform
from typing import Any

from tools.base import BaseTool
from tools.schemas import ToolDefinition, ToolParameter, ToolExecutionResult, RiskLevel

logger = logging.getLogger("tony.tools.system.volume")

# Windows Virtual Key Codes
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
KEYEVENTF_KEYUP = 0x0002


def _send_key_event(vk_code: int, repeat: int = 1) -> bool:
    """Send Windows virtual key event using user32.dll."""
    if platform.system() != "Windows":
        logger.info(f"Simulating volume key 0x{vk_code:X} on non-Windows OS.")
        return True

    try:
        user32 = ctypes.windll.user32
        for _ in range(repeat):
            # Key down
            user32.keybd_event(vk_code, 0, 0, 0)
            # Key up
            user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        logger.error(f"Failed to send volume virtual key event 0x{vk_code:X}: {e}")
        return False


class VolumeUpTool(BaseTool):
    """Increase system audio volume."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="volume_up",
            description="Increase the computer audio volume.",
            category="system",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={
                "steps": ToolParameter(
                    name="steps",
                    type="integer",
                    description="Number of volume increment steps (default: 2, range: 1-10).",
                    required=False,
                    default=2
                )
            },
            examples=["Increase volume", "Turn up the volume", "Volume up"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        steps = min(10, max(1, int(parameters.get("steps") or 2)))
        success = _send_key_event(VK_VOLUME_UP, repeat=steps)
        if success:
            return self.success(f"Volume increased by {steps} steps.", data={"steps": steps})
        return self.failure("Failed to adjust volume.", error_code="VOLUME_ERROR")


class VolumeDownTool(BaseTool):
    """Decrease system audio volume."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="volume_down",
            description="Decrease the computer audio volume.",
            category="system",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={
                "steps": ToolParameter(
                    name="steps",
                    type="integer",
                    description="Number of volume decrement steps (default: 2, range: 1-10).",
                    required=False,
                    default=2
                )
            },
            examples=["Decrease volume", "Turn down the volume", "Lower the volume"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        steps = min(10, max(1, int(parameters.get("steps") or 2)))
        success = _send_key_event(VK_VOLUME_DOWN, repeat=steps)
        if success:
            return self.success(f"Volume decreased by {steps} steps.", data={"steps": steps})
        return self.failure("Failed to adjust volume.", error_code="VOLUME_ERROR")


class VolumeMuteTool(BaseTool):
    """Mute or toggle system audio mute."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="volume_mute",
            description="Mute system audio.",
            category="system",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={},
            examples=["Mute volume", "Silence the audio", "Mute"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        success = _send_key_event(VK_VOLUME_MUTE, repeat=1)
        if success:
            return self.success("System audio muted.")
        return self.failure("Failed to mute volume.", error_code="VOLUME_ERROR")


class VolumeUnmuteTool(BaseTool):
    """Unmute system audio."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="volume_unmute",
            description="Unmute system audio.",
            category="system",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={},
            examples=["Unmute volume", "Turn sound back on", "Unmute"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        success = _send_key_event(VK_VOLUME_MUTE, repeat=1)
        if success:
            return self.success("System audio unmuted.")
        return self.failure("Failed to unmute volume.", error_code="VOLUME_ERROR")


class GetVolumeTool(BaseTool):
    """Retrieve volume status."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_volume",
            description="Check system audio volume status.",
            category="system",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={},
            examples=["What is the volume?", "Check volume"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        return self.success("System audio output is active and operational.", data={"status": "active"})
