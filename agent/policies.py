"""
Security and Action Policies for TONY AI Agent Subsystem (Stage 10).
Enforces strict boundaries, risk level classification, prompt injection defenses,
untrusted content tagging, and confirmation gating.
"""
import re
from typing import Dict, Any, Tuple, Optional
from agent.models import AgentRiskLevel
from memory.extractor import is_sensitive_secret

# Disallowed dangerous commands / shell invocations
CRITICAL_COMMAND_PATTERNS = [
    re.compile(r"(?i)\b(?:powershell|cmd|bash|sh|zsh|wscript|cscript|regedit|format|diskpart)\b"),
    re.compile(r"(?i)\bformat\s+[a-z]:\b"),
    re.compile(r"(?i)\bdelete\s+(?:all|everything|c:\\|c:/)\b"),
    re.compile(r"(?i)\brmdir\s+/s\b"),
    re.compile(r"(?i)\bdel\s+/[sfq]\b"),
    re.compile(r"(?i)\bbypass\s+(?:security|controls|sandbox|confirmation)\b"),
    re.compile(r"(?i)\b(?:api_key|hf_token|secret_key|password|credential|token)\b")
]

# High-risk destructive actions requiring explicit authorization
HIGH_RISK_ACTIONS = {
    "delete_folder",
    "delete_file",
    "knowledge_delete",
    "reminder_delete_all",
    "personalization_reset"
}

# Medium-risk system state modifications
MEDIUM_RISK_ACTIONS = {
    "create_folder",
    "create_file",
    "copy_file",
    "move_file",
    "rename_file"
}

# Low-risk safe actions
LOW_RISK_ACTIONS = {
    "open_application",
    "open_website",
    "open_folder",
    "open_file",
    "search_files",
    "get_system_time",
    "get_clipboard",
    "set_clipboard",
    "volume_up",
    "volume_down",
    "volume_mute",
    "volume_unmute",
    "get_volume",
    "play_pause",
    "next_track",
    "previous_track",
    "image_generation",
    "image_edit",
    "image_regenerate",
    "text_to_video",
    "image_to_video",
    "vision_analyze",
    "vision_describe",
    "vision_question",
    "vision_ocr",
    "memory_save",
    "memory_recall",
    "memory_forget",
    "memory_clear",
    "knowledge_search",
    "knowledge_query",
    "knowledge_ask",
    "knowledge_ingest",
    "knowledge_reindex",
    "reminder_create",
    "reminder_list",
    "reminder_update",
    "reminder_delete",
    "reminder_pause",
    "reminder_resume",
    "reminder_snooze",
    "routine_run",
    "routine_create",
    "routine_list",
    "briefing_generate",
    "evening_summary_generate",
    "proactive_toggle",
    "profile_get",
    "profile_update",
    "preference_set",
    "preference_get",
    "chat"
}


class AgentSecurityPolicy:
    """Authoritative security policy manager for agent actions."""

    @classmethod
    def classify_risk(cls, action_type: str, arguments: Optional[Dict[str, Any]] = None) -> AgentRiskLevel:
        """Determine risk level of an intended action."""
        args = arguments or {}
        tool_name = args.get("tool", action_type)

        # Check for dangerous command or parameter injection
        for val in args.values():
            if isinstance(val, str):
                for pat in CRITICAL_COMMAND_PATTERNS:
                    if pat.search(val):
                        # Special case: safe file queries like search_files
                        if tool_name == "search_files":
                            continue
                        return AgentRiskLevel.CRITICAL

        if tool_name in HIGH_RISK_ACTIONS:
            return AgentRiskLevel.HIGH

        if tool_name in MEDIUM_RISK_ACTIONS:
            return AgentRiskLevel.MEDIUM

        return AgentRiskLevel.LOW

    @classmethod
    def evaluate_action(
        cls,
        action_type: str,
        arguments: Optional[Dict[str, Any]] = None,
        untrusted_source: bool = False
    ) -> Tuple[bool, Optional[str], AgentRiskLevel]:
        """
        Evaluate whether an action is permitted under agent policy.
        Returns: (is_permitted, denial_reason, risk_level)
        """
        args = arguments or {}
        tool_name = args.get("tool", action_type)
        risk = cls.classify_risk(action_type, args)

        # UNTRUSTED CONTENT GATE: Content originating from OCR/vision/web cannot trigger executable tools
        if untrusted_source and tool_name not in ("chat", "vision_question", "vision_describe"):
            return False, "Untrusted content gate: Instructions derived from image/OCR/web data are prohibited from executing system tools.", risk

        # Reject CRITICAL operations outright
        if risk == AgentRiskLevel.CRITICAL:
            return False, f"Security violation: Action '{tool_name}' contains critical risk patterns and is forbidden.", risk

        # Prohibit sensitive secret leaks in memory or arguments
        if tool_name == "memory_save":
            fact = args.get("fact", "")
            if is_sensitive_secret(fact):
                return False, "Security violation: Storing secrets, passwords, or API keys in memory is prohibited.", risk

        return True, None, risk

    @classmethod
    def requires_confirmation(cls, action_type: str, arguments: Optional[Dict[str, Any]] = None) -> bool:
        """Check if action requires explicit user authorization before execution."""
        risk = cls.classify_risk(action_type, arguments)
        return risk == AgentRiskLevel.HIGH
