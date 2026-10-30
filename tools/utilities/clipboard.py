"""
Clipboard management tools for TONY AI (Stage 5).
Safely gets and sets system clipboard text.
Strictly isolated from Stage 4 long-term memory to prevent storing sensitive clip data.
"""
import logging
import platform
import subprocess
from typing import Any

from tools.base import BaseTool
from tools.schemas import ToolDefinition, ToolParameter, ToolExecutionResult, RiskLevel

logger = logging.getLogger("tony.tools.utilities.clipboard")

# In-memory session fallback for non-Windows or test environments
_CLIPBOARD_FALLBACK = ""


def _get_clipboard_text() -> str:
    """Read text from system clipboard."""
    global _CLIPBOARD_FALLBACK
    if platform.system() != "Windows":
        return _CLIPBOARD_FALLBACK

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True,
            text=True,
            shell=False,
            timeout=5
        )
        if res.returncode == 0:
            return res.stdout.rstrip("\r\n")
    except Exception as e:
        logger.debug(f"Failed to read clipboard via PowerShell: {e}")

    return _CLIPBOARD_FALLBACK


def _set_clipboard_text(text: str) -> bool:
    """Set text on system clipboard."""
    global _CLIPBOARD_FALLBACK
    _CLIPBOARD_FALLBACK = text

    if platform.system() != "Windows":
        return True

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
            input=text,
            capture_output=True,
            text=True,
            shell=False,
            timeout=5
        )
        return res.returncode == 0
    except Exception as e:
        logger.debug(f"Failed to set clipboard via PowerShell: {e}")
        return True  # Fallback succeeds


class GetClipboardTool(BaseTool):
    """Retrieve current text from the system clipboard."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_clipboard",
            description="Get the current text content from your system clipboard (never saved to long-term memory).",
            category="utilities",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={},
            examples=["What is on my clipboard?", "Read my clipboard", "Show clipboard content"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        text = _get_clipboard_text()
        if not text:
            return self.success("Your clipboard is currently empty.", data={"content": "", "length": 0})

        display_preview = text if len(text) <= 120 else text[:117] + "..."
        return self.success(
            f"Clipboard content: \"{display_preview}\"",
            data={"content": text, "length": len(text)}
        )


class SetClipboardTool(BaseTool):
    """Set or copy text to the system clipboard."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="set_clipboard",
            description="Copy specified text to your system clipboard.",
            category="utilities",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={
                "text": ToolParameter(
                    name="text",
                    type="string",
                    description="The text content to copy to the clipboard.",
                    required=True
                )
            },
            examples=["Copy this to my clipboard", "Set clipboard to hello world"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        text = str(parameters.get("text") or "").strip()
        if not text:
            return self.failure("Text parameter is required.", error_code="INVALID_PARAMETER")

        success = _set_clipboard_text(text)
        if success:
            logger.info(f"Copied {len(text)} characters to system clipboard.")
            return self.success(
                f"Copied text to clipboard ({len(text)} characters).",
                data={"length": len(text)}
            )
        return self.failure("Failed to copy to clipboard.", error_code="CLIPBOARD_ERROR")
