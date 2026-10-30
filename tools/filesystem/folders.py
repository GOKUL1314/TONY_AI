"""
Folder management tools for TONY AI (Stage 5).
Safely creates, opens, and deletes directories within permitted user locations.
"""
import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from tools.base import BaseTool
from tools.permissions import PermissionManager
from tools.schemas import ToolDefinition, ToolParameter, ToolExecutionResult, RiskLevel

logger = logging.getLogger("tony.tools.filesystem.folders")


class CreateFolderTool(BaseTool):
    """Safely creates a new folder in an approved user directory."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="create_folder",
            description="Create a new folder in a safe user location (e.g. Desktop, Documents, Downloads).",
            category="filesystem",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={
                "name": ToolParameter(
                    name="name",
                    type="string",
                    description="The name of the new folder (e.g. 'AI Projects').",
                    required=True
                ),
                "location": ToolParameter(
                    name="location",
                    type="string",
                    description="The base location for the folder (e.g. 'Desktop', 'Documents', 'Downloads').",
                    required=False,
                    default="Desktop"
                )
            },
            examples=[
                "Tony, create a folder called Projects on my Desktop",
                "Create folder AI in Documents",
                "Make a folder called Work"
            ]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        folder_name = str(parameters.get("name") or parameters.get("target") or "").strip()
        location = str(parameters.get("location") or "Desktop").strip()

        if not folder_name:
            return self.failure("Folder name is required.", error_code="INVALID_PARAMETER")

        target_str = os.path.join(location, folder_name) if location else folder_name
        resolved_path, error = PermissionManager.resolve_safe_path(target_str, default_location="Desktop")
        if error or not resolved_path:
            return self.failure(error or "Target path is invalid.", error_code="INVALID_PATH")

        if resolved_path.exists():
            return self.failure(
                f"The folder '{resolved_path.name}' already exists at {resolved_path.parent}.",
                error_code="FOLDER_ALREADY_EXISTS",
                data={"path": str(resolved_path)}
            )

        try:
            resolved_path.mkdir(parents=True, exist_ok=False)
            logger.info(f"Created new folder: '{resolved_path}'")
            return self.success(
                f"Created folder '{resolved_path.name}' at {resolved_path.parent}.",
                data={"path": str(resolved_path), "folder_name": resolved_path.name}
            )
        except Exception as e:
            logger.error(f"Failed to create folder '{resolved_path}': {e}")
            return self.failure(f"Could not create folder: {str(e)}", error_code="FOLDER_CREATE_FAILED")


class OpenFolderTool(BaseTool):
    """Safely opens a folder in Windows File Explorer."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="open_folder",
            description="Open a specified folder in Windows File Explorer.",
            category="filesystem",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={
                "target": ToolParameter(
                    name="target",
                    type="string",
                    description="The folder path or name to open (e.g. 'Desktop', 'Downloads', 'Desktop/Projects').",
                    required=True
                )
            },
            examples=[
                "Open folder Desktop",
                "Open my Downloads folder",
                "Open folder Projects"
            ]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        target_str = str(parameters.get("target") or parameters.get("name") or "").strip()
        if not target_str:
            return self.failure("Folder target is required.", error_code="INVALID_PARAMETER")

        resolved_path, error = PermissionManager.resolve_safe_path(target_str, default_location="Desktop")
        if error or not resolved_path:
            return self.failure(error or "Folder path is invalid.", error_code="INVALID_PATH")

        if not resolved_path.exists():
            return self.failure(f"Folder '{resolved_path}' does not exist.", error_code="FOLDER_NOT_FOUND")

        if not resolved_path.is_dir():
            return self.failure(f"Target '{resolved_path}' is a file, not a directory.", error_code="NOT_A_DIRECTORY")

        try:
            subprocess.Popen(["explorer.exe", str(resolved_path)], shell=False)
            logger.info(f"Opened folder in Explorer: '{resolved_path}'")
            return self.success(
                f"Opened folder '{resolved_path.name}' in File Explorer.",
                data={"path": str(resolved_path)}
            )
        except Exception as e:
            logger.error(f"Failed to open folder '{resolved_path}': {e}")
            return self.failure(f"Could not open folder: {str(e)}", error_code="EXPLORER_FAILED")


class DeleteFolderTool(BaseTool):
    """High-risk tool to delete a folder in a safe user location. Requires explicit confirmation."""

    def __init__(self, confirmation_manager: Any = None):
        self.confirmation_manager = confirmation_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="delete_folder",
            description="Permanently delete a folder and all its contents (Requires confirmation).",
            category="filesystem",
            risk_level=RiskLevel.HIGH,
            requires_confirmation=True,
            parameters={
                "target": ToolParameter(
                    name="target",
                    type="string",
                    description="The folder path or name to delete (e.g. 'Desktop/Old_Project').",
                    required=False
                ),
                "name": ToolParameter(
                    name="name",
                    type="string",
                    description="The folder name to delete.",
                    required=False
                ),
                "location": ToolParameter(
                    name="location",
                    type="string",
                    description="The location of the folder (e.g. 'Desktop').",
                    required=False,
                    default="Desktop"
                ),
                "confirmation_token": ToolParameter(
                    name="confirmation_token",
                    type="string",
                    description="Valid unexpired confirmation token authorizing this deletion.",
                    required=False
                )
            },
            examples=["Delete folder Old_Project", "Remove folder temp"]
        )

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, str | None]:
        target = parameters.get("target") or parameters.get("name")
        if not target or not str(target).strip():
            return False, "Target folder name or path is required."
        return True, None

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        # Defense-in-depth: HIGH-risk destructive tool refuses to run without a valid confirmation token
        token = parameters.get("confirmation_token")
        if not token:
            return self.failure(
                "Action Refused: Permanent folder deletion requires a valid, unexpired confirmation token.",
                error_code="CONFIRMATION_REQUIRED"
            )
        if self.confirmation_manager:
            is_valid, err = self.confirmation_manager.validate_token(token, self.definition.name, parameters)
            if not is_valid:
                return self.failure(
                    f"Action Refused: {err}",
                    error_code="INVALID_CONFIRMATION_TOKEN"
                )

        target_str = str(parameters.get("target") or parameters.get("name") or "").strip()
        location = str(parameters.get("location") or "Desktop").strip()
        if not target_str:
            return self.failure("Folder target is required.", error_code="INVALID_PARAMETER")

        full_target = os.path.join(location, target_str) if location and not Path(target_str).is_absolute() and not any(target_str.lower().startswith(b.lower()) for b in ["desktop", "documents", "downloads", "pictures", "videos", "music"]) else target_str
        resolved_path, error = PermissionManager.resolve_safe_path(full_target, default_location="Desktop")
        if error or not resolved_path:
            return self.failure(error or "Target path is invalid.", error_code="INVALID_PATH")

        if not resolved_path.exists():
            return self.failure(f"Folder '{resolved_path}' does not exist.", error_code="FOLDER_NOT_FOUND")

        if not resolved_path.is_dir():
            return self.failure(f"Target '{resolved_path}' is not a directory.", error_code="NOT_A_DIRECTORY")

        # Refuse to delete root of safe base directories directly (e.g. don't delete entire Desktop or Downloads)
        for base in PermissionManager.get_safe_base_directories():
            if resolved_path == base:
                return self.failure(
                    f"Action Refused: Deleting top-level directory '{resolved_path.name}' is prohibited.",
                    error_code="CRITICAL_DIRECTORY_PROTECTED"
                )

        try:
            shutil.rmtree(resolved_path)
            logger.info(f"Permanently deleted folder: '{resolved_path}'")
            return self.success(
                f"Permanently deleted folder '{resolved_path.name}'.",
                data={"path": str(resolved_path)}
            )
        except Exception as e:
            logger.error(f"Failed to delete folder '{resolved_path}': {e}")
            return self.failure(f"Could not delete folder: {str(e)}", error_code="DELETE_FAILED")
