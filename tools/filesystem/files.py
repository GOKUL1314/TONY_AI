"""
File management tools for TONY AI (Stage 5).
Safely creates, opens, copies, moves, renames, and deletes files in permitted user locations.
"""
import logging
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Any

from tools.base import BaseTool
from tools.permissions import PermissionManager
from tools.schemas import ToolDefinition, ToolParameter, ToolExecutionResult, RiskLevel

logger = logging.getLogger("tony.tools.filesystem.files")

# Dangerous extensions blocked from being launched directly through OpenFileTool
DANGEROUS_EXTENSIONS = {".exe", ".bat", ".cmd", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".ps1", ".msi", ".com", ".scr"}


class CreateFileTool(BaseTool):
    """Safely creates a new text or empty file in an approved user directory."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="create_file",
            description="Create a new text file or document in a safe user location (e.g. Desktop, Documents).",
            category="filesystem",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={
                "name": ToolParameter(
                    name="name",
                    type="string",
                    description="The name of the file to create (e.g. 'notes.txt', 'todo.md').",
                    required=True
                ),
                "location": ToolParameter(
                    name="location",
                    type="string",
                    description="The base directory (e.g. 'Desktop', 'Documents').",
                    required=False,
                    default="Desktop"
                ),
                "content": ToolParameter(
                    name="content",
                    type="string",
                    description="Optional text content to write into the file.",
                    required=False,
                    default=""
                )
            },
            examples=[
                "Tony, create a file called notes.txt on my Desktop",
                "Make a file named ideas.md",
                "Create file todo.txt in Documents"
            ]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        file_name = str(parameters.get("name") or parameters.get("target") or "").strip()
        location = str(parameters.get("location") or "Desktop").strip()
        content = str(parameters.get("content") or "")

        if not file_name:
            return self.failure("File name is required.", error_code="INVALID_PARAMETER")

        target_str = os.path.join(location, file_name) if location else file_name
        resolved_path, error = PermissionManager.resolve_safe_path(target_str, default_location="Desktop")
        if error or not resolved_path:
            return self.failure(error or "Target path is invalid.", error_code="INVALID_PATH")

        if resolved_path.suffix.lower() in DANGEROUS_EXTENSIONS:
            return self.failure(
                f"Security policy: Creating executable scripts ({resolved_path.suffix}) is restricted.",
                error_code="DANGEROUS_EXTENSION"
            )

        if resolved_path.exists():
            return self.failure(
                f"File '{resolved_path.name}' already exists at {resolved_path.parent}.",
                error_code="FILE_ALREADY_EXISTS",
                data={"path": str(resolved_path)}
            )

        try:
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_path.write_text(content, encoding="utf-8")
            logger.info(f"Created new file: '{resolved_path}' ({len(content)} chars)")
            return self.success(
                f"Created file '{resolved_path.name}' at {resolved_path.parent}.",
                data={"path": str(resolved_path), "file_name": resolved_path.name}
            )
        except Exception as e:
            logger.error(f"Failed to create file '{resolved_path}': {e}")
            return self.failure(f"Could not create file: {str(e)}", error_code="FILE_CREATE_FAILED")


class OpenFileTool(BaseTool):
    """Safely opens an existing document or file using the default Windows application."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="open_file",
            description="Open a specified file using its default Windows application (e.g. document, PDF, image, text file).",
            category="filesystem",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={
                "target": ToolParameter(
                    name="target",
                    type="string",
                    description="The file name or path to open (e.g. 'Desktop/report.pdf', 'notes.txt').",
                    required=True
                )
            },
            examples=[
                "Tony, open my resume",
                "Open notes.txt",
                "Open Desktop/summary.pdf"
            ]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        target_str = str(parameters.get("target") or parameters.get("name") or "").strip()
        if not target_str:
            return self.failure("File target is required.", error_code="INVALID_PARAMETER")

        resolved_path, error = PermissionManager.resolve_safe_path(target_str, default_location="Desktop")
        if error or not resolved_path:
            return self.failure(error or "Target path is invalid.", error_code="INVALID_PATH")

        # Block direct binary execution through open_file
        if resolved_path.suffix.lower() in DANGEROUS_EXTENSIONS:
            return self.failure(
                f"Security policy: Executable files ({resolved_path.suffix}) cannot be launched via open_file. Use open_application for approved apps.",
                error_code="DANGEROUS_EXTENSION"
            )

        if not resolved_path.exists():
            return self.failure(f"File '{resolved_path.name}' was not found.", error_code="FILE_NOT_FOUND")

        if not resolved_path.is_file():
            return self.failure(f"Target '{resolved_path.name}' is a directory, not a file.", error_code="NOT_A_FILE")

        try:
            if platform.system() == "Windows":
                os.startfile(str(resolved_path))
            else:
                subprocess.Popen(["xdg-open", str(resolved_path)], shell=False)

            logger.info(f"Opened file with default application: '{resolved_path}'")
            return self.success(
                f"Opened '{resolved_path.name}'.",
                data={"path": str(resolved_path), "file_name": resolved_path.name}
            )
        except Exception as e:
            logger.error(f"Failed to open file '{resolved_path}': {e}")
            return self.failure(f"Could not open file: {str(e)}", error_code="OPEN_FAILED")


class CopyFileTool(BaseTool):
    """Copies a file to a new location in a safe directory."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="copy_file",
            description="Copy a file from one safe location to another.",
            category="filesystem",
            risk_level=RiskLevel.MEDIUM,
            requires_confirmation=False,
            parameters={
                "source": ToolParameter(name="source", type="string", description="The source file path.", required=True),
                "destination": ToolParameter(name="destination", type="string", description="The destination path or directory.", required=True)
            },
            examples=["Copy notes.txt to Documents", "Copy Desktop/report.pdf to Downloads"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        src_str = str(parameters.get("source") or "").strip()
        dst_str = str(parameters.get("destination") or "").strip()

        src_path, src_err = PermissionManager.resolve_safe_path(src_str)
        if src_err or not src_path or not src_path.exists():
            return self.failure(f"Source file invalid or not found: {src_err or src_str}", error_code="SOURCE_NOT_FOUND")

        dst_path, dst_err = PermissionManager.resolve_safe_path(dst_str)
        if dst_err or not dst_path:
            return self.failure(f"Destination path invalid: {dst_err}", error_code="INVALID_DESTINATION")

        try:
            final_dst = shutil.copy2(src_path, dst_path)
            logger.info(f"Copied file '{src_path}' to '{final_dst}'")
            return self.success(f"Copied '{src_path.name}' to '{final_dst}'.", data={"source": str(src_path), "destination": str(final_dst)})
        except Exception as e:
            return self.failure(f"Could not copy file: {str(e)}", error_code="COPY_FAILED")


class MoveFileTool(BaseTool):
    """Moves a file to a new location in a safe directory."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="move_file",
            description="Move a file from one safe location to another.",
            category="filesystem",
            risk_level=RiskLevel.MEDIUM,
            requires_confirmation=False,
            parameters={
                "source": ToolParameter(name="source", type="string", description="The source file path.", required=True),
                "destination": ToolParameter(name="destination", type="string", description="The destination path or directory.", required=True)
            },
            examples=["Move notes.txt to Documents", "Move Desktop/draft.txt to Documents"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        src_str = str(parameters.get("source") or "").strip()
        dst_str = str(parameters.get("destination") or "").strip()

        src_path, src_err = PermissionManager.resolve_safe_path(src_str)
        if src_err or not src_path or not src_path.exists():
            return self.failure(f"Source file not found: {src_err or src_str}", error_code="SOURCE_NOT_FOUND")

        dst_path, dst_err = PermissionManager.resolve_safe_path(dst_str)
        if dst_err or not dst_path:
            return self.failure(f"Destination path invalid: {dst_err}", error_code="INVALID_DESTINATION")

        try:
            final_dst = shutil.move(src_path, dst_path)
            logger.info(f"Moved file '{src_path}' to '{final_dst}'")
            return self.success(f"Moved '{src_path.name}' to '{final_dst}'.", data={"source": str(src_path), "destination": str(final_dst)})
        except Exception as e:
            return self.failure(f"Could not move file: {str(e)}", error_code="MOVE_FAILED")


class RenameFileTool(BaseTool):
    """Renames an existing file in a safe directory."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="rename_file",
            description="Rename an existing file in a safe user directory.",
            category="filesystem",
            risk_level=RiskLevel.MEDIUM,
            requires_confirmation=False,
            parameters={
                "target": ToolParameter(name="target", type="string", description="The file to rename.", required=True),
                "new_name": ToolParameter(name="new_name", type="string", description="The new name for the file.", required=True)
            },
            examples=["Rename notes.txt to finished_notes.txt", "Rename draft.md to final.md"]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        target_str = str(parameters.get("target") or parameters.get("source") or "").strip()
        new_name = str(parameters.get("new_name") or "").strip()

        if not target_str or not new_name:
            return self.failure("Both 'target' (or 'source') and 'new_name' are required.", error_code="INVALID_PARAMETER")

        target_path, err = PermissionManager.resolve_safe_path(target_str)
        if err or not target_path or not target_path.exists():
            return self.failure(f"Target file not found: {err or target_str}", error_code="FILE_NOT_FOUND")

        new_path = target_path.parent / new_name
        if new_path.exists():
            return self.failure(f"A file named '{new_name}' already exists in that location.", error_code="FILE_ALREADY_EXISTS")

        try:
            target_path.rename(new_path)
            logger.info(f"Renamed file '{target_path.name}' to '{new_name}'")
            return self.success(f"Renamed '{target_path.name}' to '{new_name}'.", data={"old_name": target_path.name, "new_name": new_name})
        except Exception as e:
            return self.failure(f"Could not rename file: {str(e)}", error_code="RENAME_FAILED")


class DeleteFileTool(BaseTool):
    """High-risk tool to permanently delete a file. Requires explicit confirmation."""

    def __init__(self, confirmation_manager: Any = None):
        self.confirmation_manager = confirmation_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="delete_file",
            description="Permanently delete a specified file (Requires confirmation).",
            category="filesystem",
            risk_level=RiskLevel.HIGH,
            requires_confirmation=True,
            parameters={
                "target": ToolParameter(
                    name="target",
                    type="string",
                    description="The file name or path to delete (e.g. 'Desktop/test.txt').",
                    required=False
                ),
                "name": ToolParameter(
                    name="name",
                    type="string",
                    description="The file name to delete.",
                    required=False
                ),
                "location": ToolParameter(
                    name="location",
                    type="string",
                    description="The location of the file (e.g. 'Desktop').",
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
            examples=[
                "Delete file test.txt",
                "Remove report.pdf",
                "Delete Desktop/old_notes.txt"
            ]
        )

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, str | None]:
        target = parameters.get("target") or parameters.get("name")
        if not target or not str(target).strip():
            return False, "Target file name or path is required."
        return True, None

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        # Defense-in-depth: HIGH-risk destructive tool refuses to run without a valid confirmation token
        token = parameters.get("confirmation_token")
        if not token:
            return self.failure(
                "Action Refused: Permanent file deletion requires a valid, unexpired confirmation token.",
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
            return self.failure("File target is required.", error_code="INVALID_PARAMETER")

        full_target = os.path.join(location, target_str) if location and not Path(target_str).is_absolute() and not any(target_str.lower().startswith(b.lower()) for b in ["desktop", "documents", "downloads", "pictures", "videos", "music"]) else target_str
        resolved_path, error = PermissionManager.resolve_safe_path(full_target, default_location="Desktop")
        if error or not resolved_path:
            return self.failure(error or "Target path is invalid.", error_code="INVALID_PATH")

        if not resolved_path.exists():
            return self.failure(f"File '{resolved_path.name}' does not exist.", error_code="FILE_NOT_FOUND")

        if not resolved_path.is_file():
            return self.failure(f"Target '{resolved_path.name}' is a directory, not a file. Use delete_folder.", error_code="NOT_A_FILE")

        try:
            os.remove(resolved_path)
            logger.info(f"Permanently deleted file: '{resolved_path}'")
            return self.success(
                f"Permanently deleted file '{resolved_path.name}'.",
                data={"path": str(resolved_path), "file_name": resolved_path.name}
            )
        except Exception as e:
            logger.error(f"Failed to delete file '{resolved_path}': {e}")
            return self.failure(f"Could not delete file: {str(e)}", error_code="DELETE_FAILED")
