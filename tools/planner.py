"""
Tool Planner for TONY AI (Stage 5).
Parses natural language user utterances into structured, validated tool plans.
Ensures conversational queries do not trigger tools and validates parameters against registered schemas.
"""
import logging
import re
from typing import Any

from tools.registry import ToolRegistry
from tools.system.applications import APPROVED_APPLICATIONS
from tools.browser.browser import KNOWN_SERVICES
from intelligence.target_scope import analyze_target_scope

logger = logging.getLogger("tony.tools.planner")

# Leading address prefixes to remove
CLEAN_PREFIX_RE = re.compile(
    r"^(?:tony[,!:]?\s*|hey\s+tony[,!:]?\s*|hi\s+tony[,!:]?\s*|please\s+|can\s+you\s+(?:please\s+)?|could\s+you\s+(?:please\s+)?)+",
    re.IGNORECASE
)


class ToolPlanner:
    """Translates user natural language dialogue turns into structured tool execution plans."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def plan(self, text: str) -> dict[str, Any] | None:
        """
        Analyze user text and return a structured tool request:
        {"tool": "<tool_name>", "parameters": {...}}
        Returns None if text is conversational or does not request a tool action.
        """
        clean = text.strip()
        if not clean:
            return None

        # Strip prefixes like "Tony, ", "Hey Tony, please "
        cmd = CLEAN_PREFIX_RE.sub("", clean).strip()

        # 1. System Time & Date
        if re.search(r"\b(?:what\s+time\s+is\s+it|what\s+is\s+the\s+time|current\s+time|tell\s+me\s+the\s+time|what\s+is\s+today'?s\s+date|what\s+date\s+is\s+it|what\s+day\s+is\s+it\s+today|what\s+day\s+is\s+it)\b", cmd, re.IGNORECASE):
            return {"tool": "get_system_time", "parameters": {}}

        # 2. Volume & Audio Controls
        if re.search(r"\b(?:increase\s+(?:the\s+)?volume|volume\s+up|turn\s+up\s+(?:the\s+)?volume|make\s+it\s+louder|louder)\b", cmd, re.IGNORECASE):
            steps_match = re.search(r"\b(?:by\s+)?(\d+)\s*(?:steps?|percent|%)?\b", cmd)
            steps = int(steps_match.group(1)) if steps_match else 2
            return {"tool": "volume_up", "parameters": {"steps": steps}}

        if re.search(r"\b(?:decrease\s+(?:the\s+)?volume|volume\s+down|turn\s+down\s+(?:the\s+)?volume|lower\s+(?:the\s+)?volume|quieter)\b", cmd, re.IGNORECASE):
            steps_match = re.search(r"\b(?:by\s+)?(\d+)\s*(?:steps?|percent|%)?\b", cmd)
            steps = int(steps_match.group(1)) if steps_match else 2
            return {"tool": "volume_down", "parameters": {"steps": steps}}

        if re.search(r"^(?:mute(?:\s+(?:the\s+)?volume)?|silence(?:\s+the\s+audio)?|mute\s+audio)$", cmd, re.IGNORECASE):
            return {"tool": "volume_mute", "parameters": {}}

        if re.search(r"^(?:unmute(?:\s+(?:the\s+)?volume)?|turn\s+sound\s+back\s+on)$", cmd, re.IGNORECASE):
            return {"tool": "volume_unmute", "parameters": {}}

        if re.search(r"\b(?:what\s+is\s+the\s+volume|check\s+volume|get\s+volume)\b", cmd, re.IGNORECASE):
            return {"tool": "get_volume", "parameters": {}}

        # 3. Media Controls
        if re.search(r"\b(?:pause\s+(?:the\s+)?(?:music|playback|song|media)|resume\s+(?:the\s+)?(?:music|playback|song|media)|play\s+(?:the\s+)?(?:music|song|media)|play\s+pause)\b", cmd, re.IGNORECASE):
            return {"tool": "play_pause", "parameters": {}}

        if re.search(r"\b(?:next\s+(?:track|song)|skip\s+(?:track|song|this\s+song))\b", cmd, re.IGNORECASE):
            return {"tool": "next_track", "parameters": {}}

        if re.search(r"\b(?:previous\s+(?:track|song)|last\s+(?:track|song)|go\s+back\s+a\s+song)\b", cmd, re.IGNORECASE):
            return {"tool": "previous_track", "parameters": {}}

        # 4. Clipboard Tools
        if re.search(r"\b(?:what(?:'s|\s+is)\s+(?:on|in)\s+(?:my\s+)?clipboard|read\s+(?:my\s+)?clipboard|get\s+(?:my\s+)?clipboard|show\s+(?:my\s+)?clipboard|check\s+(?:my\s+)?clipboard)\b", cmd, re.IGNORECASE):
            return {"tool": "get_clipboard", "parameters": {}}

        set_clip_match = re.search(r"^(?:copy\s+(?:this\s+)?(?:text\s+)?to\s+(?:my\s+)?clipboard\s*[:\-]?\s*|set\s+clipboard\s+to\s+)(.+)$", cmd, re.IGNORECASE)
        if set_clip_match:
            text_to_copy = set_clip_match.group(1).strip()
            return {"tool": "set_clipboard", "parameters": {"text": text_to_copy}}

        # 5. Website Launching (e.g. "open YouTube", "go to Google", "open github.com")
        open_web_match = re.search(r"^(?:open|go\s+to|launch|browse\s+to)\s+(?:website\s+|site\s+)?([a-zA-Z0-9_\-\.\:\/]+(?:\s+[a-zA-Z0-9_\-\.\:\/]+)?)$", cmd, re.IGNORECASE)
        if open_web_match:
            target = open_web_match.group(1).strip().strip(" .,!?:;")
            target_lower = target.lower()

            # Check if target is a known website or ends in a web TLD or starts with http
            is_known_web = target_lower in KNOWN_SERVICES
            has_web_domain = any(target_lower.endswith(tld) for tld in [".com", ".org", ".net", ".io", ".dev", ".ai", ".edu", ".gov", ".co"])
            has_http = target_lower.startswith(("http://", "https://", "www."))

            if (is_known_web or has_web_domain or has_http) and target_lower not in APPROVED_APPLICATIONS:
                return {"tool": "open_website", "parameters": {"target": target, "url": target}}

        # 6. Windows Applications Launching (e.g. "open Notepad", "start Calculator", "launch Chrome")
        open_app_match = re.search(r"^(?:open|launch|start|run)\s+(?:application\s+|app\s+|program\s+)?([a-zA-Z0-9_\-\.\s]+?)$", cmd, re.IGNORECASE)
        if open_app_match:
            app_candidate = open_app_match.group(1).strip().strip(" .,!?:;").lower()
            if app_candidate in APPROVED_APPLICATIONS:
                return {"tool": "open_application", "parameters": {"application": app_candidate}}

        # 7. Folder Creation (e.g. "create a folder called Projects on my Desktop", "make folder AI in Documents")
        create_folder_match = re.search(
            r"^(?:create|make|new)\s+(?:a\s+)?folder\s+(?:called\s+|named\s+)?([a-zA-Z0-9_\-\.\s]+?)(?:\s+(?:on|in|at)\s+(?:my\s+)?([a-zA-Z0-9_\-\.\s]+))?$",
            cmd,
            re.IGNORECASE
        )
        if create_folder_match:
            fname = create_folder_match.group(1).strip(" \"'")
            location = create_folder_match.group(2).strip(" \"'").lower() if create_folder_match.group(2) else "desktop"
            return {"tool": "create_folder", "parameters": {"name": fname, "location": location}}

        # 8. File Creation (e.g. "create a file called notes.txt on my Desktop", "make file ideas.md")
        create_file_match = re.search(
            r"^(?:create|make|new)\s+(?:a\s+)?file\s+(?:called\s+|named\s+)?([a-zA-Z0-9_\-\.\s]+?)(?:\s+(?:on|in|at)\s+(?:my\s+)?([a-zA-Z0-9_\-\.\s]+))?$",
            cmd,
            re.IGNORECASE
        )
        if create_file_match:
            fname = create_file_match.group(1).strip(" \"'")
            location = create_file_match.group(2).strip(" \"'").lower() if create_file_match.group(2) else "desktop"
            return {"tool": "create_file", "parameters": {"name": fname, "location": location}}

        # 9. Search Files (requires search verb AND positive evidence of local storage target)
        if re.match(r"^(?:find|search|locate|where\s+is)\b", cmd, re.IGNORECASE):
            scope = analyze_target_scope(cmd)
            if scope.is_local_file and not scope.is_compound and scope.query:
                query_clean = scope.query.strip(" \"'")
                # Exclude basic interrogatives like "who am i", "what is python"
                if query_clean.lower() not in {"my name", "you", "tony", "python", "ai", "this", "it"}:
                    return {"tool": "search_files", "parameters": {"query": query_clean, "location": scope.location}}
            elif scope.rejected_tool:
                logger.debug(f"ToolPlanner rejected search_files for '{cmd}': {scope.rejection_reason}")

        # 10. Open Folder in Explorer (e.g. "open folder Desktop", "open my Downloads folder")
        open_folder_match = re.search(
            r"^open\s+(?:my\s+)?(?:folder\s+|directory\s+)([a-zA-Z0-9_\-\.\/\\]+)$|^open\s+(?:my\s+)?([a-zA-Z0-9_\-\.\/\\]+)\s+folder$",
            cmd,
            re.IGNORECASE
        )
        if open_folder_match:
            target_f = (open_folder_match.group(1) or open_folder_match.group(2) or "").strip()
            return {"tool": "open_folder", "parameters": {"target": target_f}}

        # 11. Open Document/File (e.g. "open file notes.txt", "open report.pdf")
        open_doc_match = re.search(
            r"^open\s+(?:my\s+)?(?:file\s+|document\s+)?([a-zA-Z0-9_\-\.\/\\]+\.[a-zA-Z0-9]+)$",
            cmd,
            re.IGNORECASE
        )
        if open_doc_match:
            target_f = open_doc_match.group(1).strip()
            return {"tool": "open_file", "parameters": {"target": target_f}}

        # 12. Delete File (e.g. "delete file test.txt", "trash eval_note.txt", "get rid of file x.txt", "wipe log.txt")
        delete_file_match = re.search(
            r"^(?:delete|remove|erase|wipe|trash|get\s+rid\s+of|destroy)\s+(?:the\s+)?(?:file\s+)?(?:called\s+|named\s+)?[\"']?([a-zA-Z0-9_\-\.\/\\]+\.[a-zA-Z0-9]+)[\"']?(?:\s+(?:on|in|at|from)\s+(?:my\s+)?([a-zA-Z0-9_\-\.\s]+))?$",
            cmd,
            re.IGNORECASE
        )
        if not delete_file_match:
            delete_file_match = re.search(
                r"^(?:delete|remove|erase|wipe|trash|get\s+rid\s+of|destroy)\s+(?:from|on|in|at)\s+(?:my\s+)?([a-zA-Z0-9_\-\.\s]+?)\s+(?:the\s+)?(?:file\s+)?(?:called\s+|named\s+)?[\"']?([a-zA-Z0-9_\-\.\/\\]+\.[a-zA-Z0-9]+)[\"']?$",
                cmd,
                re.IGNORECASE
            )
            if delete_file_match:
                loc = delete_file_match.group(1).strip().strip("\"'")
                fname = delete_file_match.group(2).strip().strip("\"'")
                target_f = f"{loc}/{fname}" if loc and "/" not in fname and "\\" not in fname else fname
                return {"tool": "delete_file", "parameters": {"target": target_f, "name": fname, "location": loc}}
        else:
            fname = delete_file_match.group(1).strip().strip("\"'")
            loc = delete_file_match.group(2).strip().strip("\"'") if delete_file_match.group(2) else "Desktop"
            target_f = f"{loc}/{fname}" if loc and "/" not in fname and "\\" not in fname else fname
            return {"tool": "delete_file", "parameters": {"target": target_f, "name": fname, "location": loc}}

        # 13. Delete Folder (e.g. "delete folder Old_Project", "trash folder Temp", "get rid of directory X", "wipe folder Y")
        delete_folder_match = re.search(
            r"^(?:delete|remove|erase|wipe|trash|get\s+rid\s+of|destroy)\s+(?:the\s+)?(?:folder|directory)\s+(?:called\s+|named\s+)?[\"']?([a-zA-Z0-9_\-\.\/\\]+)[\"']?(?:\s+(?:on|in|at|from)\s+(?:my\s+)?([a-zA-Z0-9_\-\.\s]+))?$",
            cmd,
            re.IGNORECASE
        )
        if not delete_folder_match:
            delete_folder_match = re.search(
                r"^(?:delete|remove|erase|wipe|trash|get\s+rid\s+of|destroy)\s+(?:the\s+)?[\"']?([a-zA-Z0-9_\-\.\/\\]+)[\"']?\s+(?:folder|directory)(?:\s+(?:on|in|at|from)\s+(?:my\s+)?([a-zA-Z0-9_\-\.\s]+))?$",
                cmd,
                re.IGNORECASE
            )
        if not delete_folder_match:
            delete_folder_match = re.search(
                r"^(?:delete|remove|erase|wipe|trash|get\s+rid\s+of|destroy)\s+(?:from|on|in|at)\s+(?:my\s+)?([a-zA-Z0-9_\-\.\s]+?)\s+(?:the\s+)?(?:folder|directory)\s+(?:called\s+|named\s+)?[\"']?([a-zA-Z0-9_\-\.\/\\]+)[\"']?$",
                cmd,
                re.IGNORECASE
            )
            if delete_folder_match:
                loc = delete_folder_match.group(1).strip().strip("\"'")
                fol_name = delete_folder_match.group(2).strip().strip("\"'")
                target_f = f"{loc}/{fol_name}" if loc and "/" not in fol_name and "\\" not in fol_name else fol_name
                return {"tool": "delete_folder", "parameters": {"target": target_f, "name": fol_name, "location": loc}}
        else:
            fol_name = delete_folder_match.group(1).strip().strip("\"'")
            loc = delete_folder_match.group(2).strip().strip("\"'") if delete_folder_match.group(2) else "Desktop"
            target_f = f"{loc}/{fol_name}" if loc and "/" not in fol_name and "\\" not in fol_name else fol_name
            return {"tool": "delete_folder", "parameters": {"target": target_f, "name": fol_name, "location": loc}}

        # No tool directive matched -> general conversational turn
        return None

    def validate_plan(self, plan: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate that the generated plan refers to a registered tool with valid schema parameters."""
        tool_name = plan.get("tool")
        if not tool_name or not self.registry.is_registered(tool_name):
            return False, f"Planned tool '{tool_name}' is not registered."

        tool = self.registry.get_tool(tool_name)
        params = plan.get("parameters", {})
        return tool.validate_parameters(params)
