"""
Progress tracking and status indicators for TONY AI Video Generation (Stage 7).
Accurately reports real percentage progress when provided, or maintains clear indeterminate
progress without fabricating fake percentages.
"""
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class ProgressUpdate:
    """Represents a discrete progress update."""
    percentage: Optional[int]  # 0-100 or None for indeterminate
    message: str
    is_indeterminate: bool = False

    @classmethod
    def determinate(cls, percentage: int, message: str) -> "ProgressUpdate":
        clamped = max(0, min(100, int(percentage)))
        return cls(percentage=clamped, message=message, is_indeterminate=False)

    @classmethod
    def indeterminate(cls, message: str = "Processing video...") -> "ProgressUpdate":
        return cls(percentage=None, message=message, is_indeterminate=True)


class ProgressTracker:
    """Helper for passing status callbacks from video providers to asynchronous job handlers."""

    def __init__(self, callback: Optional[Callable[[ProgressUpdate], None]] = None):
        self.callback = callback
        self.latest_update = ProgressUpdate.indeterminate("Queued")

    def update(self, percentage: Optional[int], message: str) -> None:
        """Receive progress report and trigger callback."""
        if percentage is not None:
            self.latest_update = ProgressUpdate.determinate(percentage, message)
        else:
            self.latest_update = ProgressUpdate.indeterminate(message)

        if self.callback:
            try:
                self.callback(self.latest_update)
            except Exception:
                pass
