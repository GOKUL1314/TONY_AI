"""
Code and Patch Validator for TONY AI Self-Upgrade Subsystem.
Validates syntax via Python AST and enforces security compliance before patch application.
"""
import ast
from pathlib import Path
import logging

from self_upgrade.policy import UpgradeSecurityPolicy
from self_upgrade.errors import PatchValidationError

logger = logging.getLogger("tony.self_upgrade.validator")


class PatchValidator:
    """Performs static syntax and safety verification on proposed changes."""

    @classmethod
    def validate_content(cls, content: str, file_path: str) -> bool:
        """
        Validate that the proposed file content is syntactically sound and policy-compliant.
        """
        # 1. Security Policy Verification
        UpgradeSecurityPolicy.validate_code_safety(content, file_name=file_path)

        # 2. Python AST Syntax Check for .py files
        if file_path.endswith(".py"):
            try:
                ast.parse(content, filename=file_path)
            except SyntaxError as e:
                logger.error(f"Syntax validation failed for '{file_path}': line {e.lineno}: {e.msg}")
                raise PatchValidationError(f"Syntax error in candidate code for '{file_path}': line {e.lineno}: {e.msg}")

        return True
