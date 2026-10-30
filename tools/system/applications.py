"""
Application control tool for TONY AI (Stage 5).
Safely launches approved Windows applications using a strict allowlist.
"""
import logging
import os
import shutil
import subprocess
from typing import Any

from tools.base import BaseTool
from tools.schemas import ToolDefinition, ToolParameter, ToolExecutionResult, RiskLevel

logger = logging.getLogger("tony.tools.system.applications")

# Approved application allowlist and their standard executables / protocol aliases
APPROVED_APPLICATIONS: dict[str, list[str]] = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "paint": ["mspaint.exe"],
    "mspaint": ["mspaint.exe"],
    "explorer": ["explorer.exe"],
    "file explorer": ["explorer.exe"],
    "cmd": ["cmd.exe"],
    "command prompt": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "chrome": ["chrome.exe", "google chrome"],
    "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "firefox": ["firefox.exe"],
    "vscode": ["code.cmd", "code.exe", "code"],
    "code": ["code.cmd", "code.exe", "code"],
    "vs code": ["code.cmd", "code.exe", "code"],
    "taskmgr": ["taskmgr.exe"],
    "task manager": ["taskmgr.exe"],
}


class OpenApplicationTool(BaseTool):
    """Safely opens an approved Windows application from the allowlist."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="open_application",
            description="Launch an approved Windows desktop application (e.g. Notepad, Calculator, Chrome, VS Code).",
            category="system",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={
                "application": ToolParameter(
                    name="application",
                    type="string",
                    description="The name of the application to launch (e.g. 'notepad', 'calculator', 'chrome', 'vscode').",
                    required=True
                )
            },
            examples=[
                "Tony, open Notepad",
                "Launch calculator",
                "Open Chrome",
                "Start VS Code"
            ]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        app_name = str(parameters.get("application", "")).strip().lower()
        if not app_name:
            return self.failure("Application name is required.", error_code="INVALID_PARAMETER")

        # 1. Check allowlist
        if app_name not in APPROVED_APPLICATIONS:
            allowed_list = ", ".join(sorted(set(k.title() for k in ["Notepad", "Calculator", "Paint", "Explorer", "Chrome", "Edge", "Firefox", "VS Code"])))
            return self.failure(
                f"Application '{app_name}' is not in the approved application allowlist. Approved applications include: {allowed_list}.",
                error_code="APPLICATION_NOT_ALLOWED"
            )

        executable_candidates = APPROVED_APPLICATIONS[app_name]
        chosen_exe = None

        # 2. Locate executable
        for cand in executable_candidates:
            which_path = shutil.which(cand)
            if which_path:
                chosen_exe = which_path
                break
            # Check system32
            sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", cand)
            if os.path.exists(sys32):
                chosen_exe = sys32
                break

        # Fallback to candidate name for standard Windows registered binaries
        if not chosen_exe:
            chosen_exe = executable_candidates[0]

        try:
            # Safe launch: never use shell=True
            subprocess.Popen([chosen_exe], shell=False)
            logger.info(f"Successfully launched application '{app_name}' via binary: {chosen_exe}")
            return self.success(
                f"Opened {app_name.title()}.",
                data={"application": app_name, "executable": chosen_exe}
            )
        except Exception as e:
            logger.error(f"Failed to launch application '{app_name}': {e}")
            return self.failure(
                f"Could not open {app_name.title()}: {str(e)}",
                error_code="LAUNCH_FAILED"
            )
