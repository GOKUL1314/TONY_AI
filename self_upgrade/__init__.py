"""
TONY AI Controlled Self-Upgrade Subsystem.
Enables safe, policy-guarded architectural improvements with automatic backups,
AST syntax validation, test verification, and automated rollbacks.
"""
from self_upgrade.models import (
    UpgradePlan,
    UpgradeStep,
    UpgradeStatus,
    RiskLevel,
    DiagnosticReport,
    BackupRecord,
    TestRunResult
)
from self_upgrade.policy import UpgradeSecurityPolicy
from self_upgrade.errors import (
    SelfUpgradeError,
    SecurityViolationError,
    ProtectedFileError,
    PatchValidationError,
    BackupError,
    TestFailureError,
    RollbackError
)
from self_upgrade.backup import BackupManager
from self_upgrade.analyzer import ProjectAnalyzer
from self_upgrade.planner import UpgradePlanner
from self_upgrade.validator import PatchValidator
from self_upgrade.patcher import CodePatcher
from self_upgrade.tester import UpgradeTestRunner
from self_upgrade.history import UpgradeHistoryManager
from self_upgrade.manager import SelfUpgradeManager

__all__ = [
    "UpgradePlan",
    "UpgradeStep",
    "UpgradeStatus",
    "RiskLevel",
    "DiagnosticReport",
    "BackupRecord",
    "TestRunResult",
    "UpgradeSecurityPolicy",
    "SelfUpgradeError",
    "SecurityViolationError",
    "ProtectedFileError",
    "PatchValidationError",
    "BackupError",
    "TestFailureError",
    "RollbackError",
    "BackupManager",
    "ProjectAnalyzer",
    "UpgradePlanner",
    "PatchValidator",
    "CodePatcher",
    "UpgradeTestRunner",
    "UpgradeHistoryManager",
    "SelfUpgradeManager"
]
