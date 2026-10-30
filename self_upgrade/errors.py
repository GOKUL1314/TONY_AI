"""
Custom Exceptions for TONY AI Self-Upgrade Subsystem.
"""


class SelfUpgradeError(Exception):
    """Base exception for all self-upgrade subsystem errors."""
    pass


class SecurityViolationError(SelfUpgradeError):
    """Raised when an upgrade attempts to bypass security, access credentials, or execute prohibited shell operations."""
    pass


class ProtectedFileError(SecurityViolationError):
    """Raised when an upgrade targets a protected file (.env, .git, venv, databases)."""
    pass


class PatchValidationError(SelfUpgradeError):
    """Raised when candidate code fails AST parsing or contains unsafe constructs."""
    pass


class BackupError(SelfUpgradeError):
    """Raised when creating or restoring a checkpoint fails."""
    pass


class TestFailureError(SelfUpgradeError):
    """Raised when test verification fails after applying a patch."""
    pass


class RollbackError(SelfUpgradeError):
    """Raised when restoring from backup fails."""
    pass
