"""
Test Execution and Verification Engine for TONY AI Self-Upgrade Subsystem.
Safely executes unit tests and full regression suites to objectively verify code changes.
"""
import sys
import subprocess
import time
import re
from pathlib import Path
import logging
from typing import Optional, List

from self_upgrade.models import TestRunResult

logger = logging.getLogger("tony.self_upgrade.tester")


class UpgradeTestRunner:
    """Executes tests using project Python virtual environment without shell execution."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        # Detect venv python
        venv_py = project_root / "venv" / "Scripts" / "python.exe"
        if venv_py.exists():
            self.python_exe = str(venv_py)
        else:
            self.python_exe = sys.executable

    def run_tests(self, target_test: Optional[str] = None, timeout: int = 120) -> TestRunResult:
        """
        Execute python unittest on a specific test file or full discovery.
        Uses explicit argument lists (no shell=True) for security.
        """
        cmd: List[str] = [self.python_exe, "-m", "unittest"]
        if target_test:
            cmd.append(target_test)
        else:
            cmd.extend(["discover", "tests"])

        start_time = time.time()
        try:
            logger.info(f"Running test verification command: {' '.join(cmd)}")
            proc = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False  # Security invariant: No shell execution
            )
            duration = time.time() - start_time
            raw_output = (proc.stdout or "") + "\n" + (proc.stderr or "")

            # Parse results from unittest output
            # e.g.: "Ran 355 tests in 52.707s\n\nOK (skipped=1)" or "FAILED (failures=1, errors=1)"
            total_match = re.search(r"Ran (\d+) tests? in", raw_output)
            total = int(total_match.group(1)) if total_match else 0

            passed = total
            failed = 0
            errors = 0
            skipped = 0

            fail_match = re.search(r"failures=(\d+)", raw_output)
            if fail_match:
                failed = int(fail_match.group(1))

            err_match = re.search(r"errors=(\d+)", raw_output)
            if err_match:
                errors = int(err_match.group(1))

            skip_match = re.search(r"skipped=(\d+)", raw_output)
            if skip_match:
                skipped = int(skip_match.group(1))

            passed = max(0, total - (failed + errors + skipped))
            success = (proc.returncode == 0) and (failed == 0) and (errors == 0)

            return TestRunResult(
                total=total,
                passed=passed,
                failed=failed,
                errors=errors,
                skipped=skipped,
                duration_seconds=duration,
                success=success,
                output_summary=raw_output[-1500:]  # Keep last 1500 chars
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            logger.error("Test execution timed out.")
            return TestRunResult(
                total=0,
                passed=0,
                failed=1,
                errors=1,
                duration_seconds=duration,
                success=False,
                output_summary="Test execution timed out."
            )
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Test runner error: {e}")
            return TestRunResult(
                total=0,
                passed=0,
                failed=1,
                errors=1,
                duration_seconds=duration,
                success=False,
                output_summary=str(e)
            )
