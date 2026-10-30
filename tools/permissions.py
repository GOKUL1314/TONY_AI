"""
Permission, path safety, and risk classification engine for TONY AI (Stage 5).
Ensures safe Windows automation by preventing path traversal, blocking system directory modification,
and strictly validating URLs and targets.
"""
import logging
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from tools.schemas import RiskLevel

logger = logging.getLogger("tony.tools.permissions")

# Safe base user directories where TONY is permitted to read and write
USER_HOME = Path.home().resolve()

SAFE_BASE_NAMES = {
    "desktop": USER_HOME / "Desktop",
    "documents": USER_HOME / "Documents",
    "downloads": USER_HOME / "Downloads",
    "pictures": USER_HOME / "Pictures",
    "videos": USER_HOME / "Videos",
    "music": USER_HOME / "Music",
}

# Project root is also safe for sandbox operations
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Strictly protected paths: Any modification attempt is CRITICAL and REFUSED
PROTECTED_SYSTEM_DIRECTORIES = [
    Path(os.environ.get("SystemRoot", r"C:\Windows")),
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
    Path(r"C:\ProgramData"),
    USER_HOME,  # Don't allow deleting/overwriting the root user profile directly
]

# Forbidden shell injection patterns
SHELL_INJECTION_PATTERN = re.compile(r"[;&|`$><\r\n]")

# Forbidden URL schemes
FORBIDDEN_URL_SCHEMES = {"file", "javascript", "data", "vbscript", "about"}


class PermissionManager:
    """Enforces path safety, dangerous protocol rejection, and action risk assessment."""

    @classmethod
    def get_safe_base_directories(cls) -> list[Path]:
        """Return list of safe user base directories."""
        dirs = [d for d in SAFE_BASE_NAMES.values() if d.exists()]
        dirs.append(PROJECT_ROOT)
        return dirs

    @classmethod
    def resolve_safe_path(cls, user_path_str: str, default_location: str = "Desktop") -> tuple[Path | None, str | None]:
        """
        Safely resolve a user-supplied path string against allowed safe directories.
        Prevents path traversal ('..') and access to protected Windows system directories.
        Returns (resolved_path, error_message).
        """
        if not user_path_str or not user_path_str.strip():
            return None, "Path cannot be empty."

        clean_path = user_path_str.strip().strip("\"'")

        # 1. Path traversal check
        if ".." in clean_path or clean_path.startswith("/") or clean_path.startswith("\\"):
            # Check for explicit traversal
            if ".." in clean_path.replace("\\", "/").split("/"):
                logger.warning(f"Security Alert: Path traversal attempt detected: '{clean_path}'")
                return None, "Path traversal ('..') is strictly forbidden for system security."

        # 2. Check if user specified a named safe location prefix (e.g. 'Desktop/Projects', 'Downloads/report.pdf')
        matched_base = None
        relative_part = clean_path

        lower_path = clean_path.lower().replace("\\", "/")
        for name, base_path in SAFE_BASE_NAMES.items():
            if lower_path.startswith(f"{name}/") or lower_path == name:
                matched_base = base_path
                relative_part = clean_path[len(name):].lstrip("/\\")
                break

        # 3. If an absolute path was passed
        if Path(clean_path).is_absolute():
            resolved = Path(clean_path).resolve()
        elif matched_base:
            resolved = (matched_base / relative_part).resolve()
        else:
            # Fall back to default location (usually Desktop or Downloads)
            base = SAFE_BASE_NAMES.get(default_location.lower(), SAFE_BASE_NAMES["desktop"])
            resolved = (base / clean_path).resolve()

        # 4. Verify resolved path is within an allowed safe directory
        is_safe = False
        for safe_base in cls.get_safe_base_directories():
            try:
                if resolved == safe_base or safe_base in resolved.parents:
                    is_safe = True
                    break
            except Exception:
                pass

        if not is_safe:
            logger.warning(f"Security Alert: Target '{resolved}' is outside permitted safe directories.")
            return None, f"Access denied: Target path must be within safe user directories (Desktop, Documents, Downloads, etc.)."

        # 5. Check if it targets protected system directories directly
        for protected in PROTECTED_SYSTEM_DIRECTORIES:
            try:
                if resolved == protected.resolve():
                    return None, f"Access denied: Operation against protected system location '{protected}' is forbidden."
            except Exception:
                pass

        return resolved, None

    @classmethod
    def validate_safe_path(cls, user_path_str: str, default_location: str = "Desktop") -> tuple[bool, str | None]:
        """Validate if a path is safe and within allowed boundaries. Returns (is_safe, error_message)."""
        resolved, error = cls.resolve_safe_path(user_path_str, default_location)
        return (resolved is not None, error)

    @classmethod
    def validate_executable_path(cls, file_name: str) -> tuple[bool, str | None]:
        """Check if target file is a forbidden executable extension."""
        dangerous_exts = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".scr", ".com"}
        ext = Path(file_name).suffix.lower()
        if ext in dangerous_exts:
            return False, f"Execution of executable extension '{ext}' is prohibited."
        return True, None

    @classmethod
    def validate_command_safety(cls, command: str) -> tuple[bool, str | None]:
        """Validate a shell command against shell metacharacters. Returns (is_safe, error_message)."""
        if cls.contains_shell_injection(command):
            return False, "Disallowed shell metacharacter detected."
        return True, None

    @classmethod
    def validate_url(cls, url: str) -> tuple[str | None, str | None]:
        """
        Validate a website URL.
        Rejects file://, javascript:, data:, and other dangerous schemes.
        Returns (normalized_url, error_message).
        """
        clean = url.strip().strip("\"'")
        if not clean:
            return None, "URL cannot be empty."

        # Check if URL explicitly defines a scheme
        if ":" in clean:
            parsed = urlparse(clean)
            scheme = (parsed.scheme or "").lower()
            if scheme in FORBIDDEN_URL_SCHEMES or scheme not in ("http", "https"):
                logger.warning(f"Security Alert: Dangerous URL scheme rejected: '{scheme}' in '{url}'")
                return None, f"Dangerous or unsupported protocol '{scheme}:'. Only HTTP and HTTPS are permitted."
        else:
            clean = "https://" + clean
            parsed = urlparse(clean)

        if not parsed.netloc:
            return None, "Invalid URL: missing domain name."

        return clean, None

    @classmethod
    def contains_shell_injection(cls, command: str) -> bool:
        """Check if an argument contains shell metacharacters."""
        return bool(SHELL_INJECTION_PATTERN.search(command))

    @classmethod
    def evaluate_risk(cls, tool_name: str, parameters: dict[str, Any]) -> RiskLevel:
        """
        Determine risk level for a proposed tool action.
        """
        # Critical keywords in parameter values or targets
        critical_keywords = {
            "format", "regedit", "powershell -enc", "del /s", "rmdir /s",
            "windows", "system32", "program files", "programdata"
        }
        for k, v in parameters.items():
            if isinstance(v, str):
                v_lower = v.lower()
                if any(crit in v_lower for crit in critical_keywords):
                    return RiskLevel.CRITICAL
                if "javascript:" in v_lower or "file:" in v_lower or "data:" in v_lower:
                    return RiskLevel.CRITICAL

        # High risk actions (destructive tools)
        if (
            tool_name in {"delete_file", "delete_folder", "bulk_delete", "overwrite_file", "knowledge_delete", "reminder_delete_all", "personalization_reset"}
            or tool_name.startswith("delete_")
            or tool_name.endswith("_delete")
        ):
            return RiskLevel.HIGH

        # Medium risk actions (moving/renaming)
        if tool_name in {"move_file", "rename_file", "close_application"}:
            return RiskLevel.MEDIUM

        # Default low risk
        return RiskLevel.LOW
