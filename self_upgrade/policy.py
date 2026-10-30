"""
Security Policy and Protective Guardrails for TONY AI Self-Upgrade Subsystem.
Strictly blocks arbitrary shell execution, protected file tampering, secret exposure,
and test-bypass manipulations.
"""
from pathlib import Path
import re
from typing import List
import logging

from self_upgrade.errors import SecurityViolationError, ProtectedFileError

logger = logging.getLogger("tony.self_upgrade.policy")


class UpgradeSecurityPolicy:
    """Enforces immutable safety constraints on self-upgrade operations."""

    # Absolute protected file and directory patterns
    PROTECTED_PATTERNS = [
        r"(?i)\.env(?:\..*)?$",
        r"(?i)(?:^|[\\/])\.git(?:[\\/]|$)",
        r"(?i)(?:^|[\\/])venv(?:[\\/]|$)",
        r"(?i)(?:^|[\\/])data[\\/]memory\.db$",
        r"(?i)(?:^|[\\/])data[\\/]knowledge(?:[\\/]|$)",
        r"(?i)(?:^|[\\/])data[\\/]personalization(?:[\\/]|$)",
        r"(?i)(?:^|[\\/])data[\\/]conversations(?:[\\/]|$)",
        r"(?i)credentials",
        r"(?i)password",
        r"(?i)secret_key",
        r"(?i)security_policy"
    ]

    # Prohibited shell execution directives
    PROHIBITED_DIRECTIVES = [
        re.compile(r"(?i)\b(?:powershell|cmd\.exe|bash|sh|zsh)\b"),
        re.compile(r"(?i)\b(?:rmdir\s+/s|rm\s+-rf|format\s+[a-z]:)\b"),
        re.compile(r"(?i)\b(?:os\.system|subprocess\.Popen|subprocess\.run|subprocess\.call)\s*\(\s*['\"](?:powershell|cmd|bash|format|del)\b"),
        re.compile(r"(?i)\b(?:disable_security|bypass_confirmation|ignore_safety)\b"),
    ]

    # Prohibited test manipulation patterns
    PROHIBITED_TEST_TAMPERING = [
        re.compile(r"(?i)def\s+test_[a-zA-Z0-9_]+\s*\([^)]*\):\s*(?:pass|return\b)"),  # Replacing test with no-op pass
        re.compile(r"(?i)@unittest\.skip\s*\("),  # Unconditionally skipping failing tests
    ]

    MAX_REPAIR_ATTEMPTS = 2

    @classmethod
    def validate_target_path(cls, file_path: str, base_dir: Path) -> Path:
        """
        Ensure file is strictly inside the project root and not in any protected path.
        """
        clean_str = file_path.replace("\\", "/")
        for pattern in cls.PROTECTED_PATTERNS:
            if re.search(pattern, clean_str):
                logger.critical(f"Security Alert: Self-upgrade target violates protected path policy: '{file_path}'")
                raise ProtectedFileError(f"File '{file_path}' is protected and cannot be modified by self-upgrade.")

        target = (base_dir / file_path).resolve()

        # Path traversal check
        try:
            target.relative_to(base_dir.resolve())
        except ValueError:
            logger.critical(f"Security Alert: Path traversal attempt in self-upgrade: '{file_path}'")
            raise SecurityViolationError("Path traversal outside project root is strictly prohibited.")

        return target

    @classmethod
    def validate_code_safety(cls, code_content: str, file_name: str = "") -> None:
        """
        Inspect candidate source code for unauthorized shell execution or security bypasses.
        """
        for pat in cls.PROHIBITED_DIRECTIVES:
            if pat.search(code_content):
                logger.critical(f"Security Alert: Prohibited shell or security-bypass pattern in code update for '{file_name}'")
                raise SecurityViolationError(
                    "Self-upgrade code contains prohibited shell commands, system formatting directives, or security bypasses."
                )

        if "test" in file_name.lower():
            for pat in cls.PROHIBITED_TEST_TAMPERING:
                if pat.search(code_content):
                    logger.critical(f"Security Alert: Prohibited test-tampering detected in '{file_name}'")
                    raise SecurityViolationError("Self-upgrade cannot delete tests or replace test bodies with dummy pass statements.")

    @classmethod
    def is_repair_allowed(cls, attempt_count: int) -> bool:
        """Enforce maximum 2 repair attempts."""
        return attempt_count < cls.MAX_REPAIR_ATTEMPTS
