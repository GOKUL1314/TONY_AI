"""
System date and time tool for TONY AI (Stage 5).
Retrieves local system time, date, day of week, and timezone.
"""
from datetime import datetime
import logging
from typing import Any

from tools.base import BaseTool
from tools.schemas import ToolDefinition, ToolExecutionResult, RiskLevel

logger = logging.getLogger("tony.tools.utilities.datetime_tool")


class GetSystemTimeTool(BaseTool):
    """Retrieves current system time and date."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_system_time",
            description="Get the current local system time, date, and day of the week.",
            category="utilities",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={},
            examples=[
                "Tony, what time is it?",
                "What is today's date?",
                "What day is it today?",
                "Current time"
            ]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        now = datetime.now()
        time_str = now.strftime("%I:%M %p").lstrip("0")
        date_str = now.strftime("%A, %B %d, %Y")

        natural_message = f"It is currently {time_str} on {date_str}."

        return self.success(
            natural_message,
            data={
                "time": time_str,
                "date": date_str,
                "iso": now.isoformat(),
                "hour": now.hour,
                "minute": now.minute,
                "day_of_week": now.strftime("%A")
            }
        )
