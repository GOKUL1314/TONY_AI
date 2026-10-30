"""
Data Models for TONY AI Controlled Self-Upgrade Subsystem.
Defines structured classes for UpgradePlan, UpgradeStep, RiskLevel, DiagnosticReport, and BackupRecord.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional
import uuid


class RiskLevel(str, Enum):
    """Risk classification for proposed software modifications."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class UpgradeStatus(str, Enum):
    """Lifecycle stages of a self-upgrade operation."""
    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    BACKED_UP = "BACKED_UP"
    APPLYING = "APPLYING"
    TESTING = "TESTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class UpgradeStep:
    """A validated, atomic file modification step."""
    step_id: str
    file_path: str
    description: str
    content: str
    original_content: Optional[str] = None
    applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "file_path": self.file_path,
            "description": self.description,
            "applied": self.applied
        }


@dataclass
class TestRunResult:
    """Outcome of a test suite execution."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    success: bool = True
    output_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "duration_seconds": round(self.duration_seconds, 2),
            "success": self.success,
            "output_summary": self.output_summary
        }


@dataclass
class UpgradePlan:
    """Structured, reviewable upgrade specification."""
    upgrade_id: str
    reason: str
    files_changed: List[str]
    steps: List[UpgradeStep] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    tests_affected: int = 0
    requires_confirmation: bool = True
    status: UpgradeStatus = UpgradeStatus.PLANNED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    backup_location: Optional[str] = None
    test_result: Optional[TestRunResult] = None
    repair_attempts: int = 0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "upgrade_id": self.upgrade_id,
            "reason": self.reason,
            "files_changed": self.files_changed,
            "steps": [s.to_dict() for s in self.steps],
            "risk_level": self.risk_level.value,
            "tests_affected": self.tests_affected,
            "requires_confirmation": self.requires_confirmation,
            "status": self.status.value,
            "created_at": self.created_at,
            "backup_location": self.backup_location,
            "test_result": self.test_result.to_dict() if self.test_result else None,
            "repair_attempts": self.repair_attempts,
            "error_message": self.error_message
        }

    @classmethod
    def create(cls, reason: str, files: List[str], risk: RiskLevel = RiskLevel.LOW) -> "UpgradePlan":
        uid = f"upg_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        return cls(
            upgrade_id=uid,
            reason=reason,
            files_changed=files,
            risk_level=risk,
            requires_confirmation=True,
            status=UpgradeStatus.PLANNED
        )


@dataclass
class BackupRecord:
    """Record of file checkpoint prior to modification."""
    upgrade_id: str
    backup_dir: str
    timestamp: str
    files_backed_up: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "upgrade_id": self.upgrade_id,
            "backup_dir": self.backup_dir,
            "timestamp": self.timestamp,
            "files_backed_up": self.files_backed_up
        }


@dataclass
class DiagnosticReport:
    """System and intelligence layer diagnostic evaluation."""
    timestamp: str
    subsystems: Dict[str, Any]
    healthy: bool
    issues: List[str]
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "subsystems": self.subsystems,
            "healthy": self.healthy,
            "issues": self.issues,
            "recommendations": self.recommendations
        }
