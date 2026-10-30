"""
Browser and Web navigation tools for TONY AI (Stage 5).
Safely opens websites in the default web browser with strict protocol validation.
"""
import logging
import webbrowser
from typing import Any

from tools.base import BaseTool
from tools.permissions import PermissionManager
from tools.schemas import ToolDefinition, ToolParameter, ToolExecutionResult, RiskLevel

logger = logging.getLogger("tony.tools.browser.browser")

# Canonical aliases for common popular web destinations
KNOWN_SERVICES: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://www.github.com",
    "gmail": "https://mail.google.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "wikipedia": "https://www.wikipedia.org",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
}


class OpenWebsiteTool(BaseTool):
    """Safely opens a website or popular web service in the user's default browser."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="open_website",
            description="Open a specified website or web service (e.g. YouTube, GitHub, Google) in the default browser.",
            category="browser",
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
            parameters={
                "url": ToolParameter(
                    name="url",
                    type="string",
                    description="The web address or service name to open (e.g. 'YouTube', 'https://github.com').",
                    required=True
                )
            },
            examples=[
                "Tony, open YouTube",
                "Open Google",
                "Go to GitHub",
                "Open https://python.org"
            ]
        )

    def execute(self, parameters: dict[str, Any]) -> ToolExecutionResult:
        raw_target = str(parameters.get("url") or parameters.get("target") or "").strip()
        if not raw_target:
            return self.failure("URL or service name is required.", error_code="INVALID_PARAMETER")

        target_lower = raw_target.lower()

        # 1. Resolve canonical service if name was provided
        if target_lower in KNOWN_SERVICES:
            final_url = KNOWN_SERVICES[target_lower]
            display_name = target_lower.title()
        else:
            # 2. Validate URL safety (blocks file://, javascript:, data:)
            valid_url, error = PermissionManager.validate_url(raw_target)
            if error or not valid_url:
                return self.failure(error or "Invalid URL.", error_code="UNSAFE_URL")
            final_url = valid_url
            display_name = raw_target

        try:
            webbrowser.open_new_tab(final_url)
            logger.info(f"Opened website in default browser: '{final_url}'")
            return self.success(
                f"Opened {display_name} in your web browser.",
                data={"url": final_url, "display_name": display_name}
            )
        except Exception as e:
            logger.error(f"Failed to open website '{final_url}': {e}")
            return self.failure(f"Could not open website: {str(e)}", error_code="BROWSER_ERROR")
