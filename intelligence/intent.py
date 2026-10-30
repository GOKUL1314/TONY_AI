"""
Intent Understanding Engine for TONY AI (Stage 8).
Parses natural language requests into structured Intent objects with entities,
confidence, required tools, and multi-step composition detection.
"""
import re
import logging
from typing import Dict, Any, List, Optional
from intelligence.models import Intent, IntentType
from intelligence.context import ConversationContext
from memory.extractor import is_sensitive_secret
from intelligence.target_scope import analyze_target_scope, split_compound_request

logger = logging.getLogger("tony.intelligence.intent")

# Leading conversational prefixes to remove
CLEAN_PREFIX_RE = re.compile(
    r"^(?:tony[,!:]?\s*|hey\s+tony[,!:]?\s*|hi\s+tony[,!:]?\s*|please\s+|can\s+you\s+(?:please\s+)?|could\s+you\s+(?:please\s+)?)+",
    re.IGNORECASE
)
# Trailing politeness or addresses
CLEAN_SUFFIX_RE = re.compile(
    r"(?:[,!:]?\s*(?:tony|please))+[.!?,]?$",
    re.IGNORECASE
)

# Prompt injection detection patterns
INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior|your)?\s*(?:instructions|rules|security|protocols|safety)\b"),
    re.compile(r"(?i)\brun\s+(?:powershell|cmd|bash|shell|terminal)\b"),
    re.compile(r"(?i)\bformat\s+[a-z]:\b"),
    re.compile(r"(?i)\bdelete\s+(?:all|everything|c:\\|c:/)\b"),
    re.compile(r"(?i)\bbypass\s+(?:security|controls|sandbox)\b"),
]


class IntentEngine:
    """Classifies user natural language input into typed, structured Intent specifications."""

    def __init__(self, tool_registry=None):
        self.tool_registry = tool_registry

    def clean_text(self, text: str) -> str:
        """Strip conversational prefixes/suffixes while preserving the core command."""
        cleaned = text.strip()
        cleaned = CLEAN_PREFIX_RE.sub("", cleaned).strip()
        cleaned = CLEAN_SUFFIX_RE.sub("", cleaned).strip().rstrip(".!?,")
        return cleaned

    def detect_intent(self, text: str, context: Optional[ConversationContext] = None) -> Intent:
        """
        Classify text and extract entities and action requirements.
        """
        if not text or not text.strip():
            return Intent(type=IntentType.UNKNOWN, confidence=0.0, user_request=text)

        clean = self.clean_text(text)
        lower = clean.lower()
        ctx = context or ConversationContext()
        ctx_refs = ctx.resolve_references(text)

        # 0. Prompt Injection / Malicious Command Override Check
        for pat in INJECTION_PATTERNS:
            if pat.search(text):
                logger.warning(f"Security Alert: Prompt injection pattern detected in input: '{text}'")
                return Intent(
                    type=IntentType.UNKNOWN,
                    confidence=1.0,
                    user_request=text,
                    entities={"security_rejection": True, "reason": "Prompt injection or prohibited shell directive detected."}
                )

        # 0b. Wake Word Only Greeting ("Tony!", "Tony", "Hey Tony")
        if not clean or re.match(r"^(?:tony|hey\s+tony|hi\s+tony|okay\s+tony)[!?,.]*$", text.lower().strip()):
            return Intent(
                type=IntentType.CHAT,
                confidence=1.0,
                user_request=text,
                entities={"wake_greeting": True}
            )

        # 0c. Self-Diagnostic, Self-Test, and Self-Upgrade Intents (Controlled Subsystem)
        if re.search(r"\b(?:run\s+(?:a\s+)?self\s+diagnostic|run\s+(?:a\s+)?health\s+check(?:\s+on\s+yourself)?|self\s+diagnostic|health\s+check)\b", lower):
            return Intent(
                type=IntentType.SELF_DIAGNOSTIC,
                confidence=1.0,
                user_request=text,
                entities={"action": "diagnose"}
            )

        if re.search(r"\b(?:run\s+(?:the\s+)?(?:test\s+suite|self\s+tests?|unit\s+tests?|regression\s+tests?)|execute\s+tests?)\b", lower):
            return Intent(
                type=IntentType.SELF_TEST,
                confidence=1.0,
                user_request=text,
                entities={"action": "test"}
            )

        if re.search(r"\b(?:self\s+status|upgrade\s+status|upgrade\s+history|show\s+upgrades?)\b", lower):
            return Intent(
                type=IntentType.SELF_STATUS,
                confidence=1.0,
                user_request=text,
                entities={"action": "status"}
            )

        if re.search(r"\b(?:analyze\s+your\s+(?:intelligence(?:\s+layer)?|code|system)|check\s+your\s+response\s+quality\s+and\s+improve\s+it|what\s+could\s+be\s+improved)\b", lower):
            return Intent(
                type=IntentType.SELF_ANALYZE,
                confidence=0.95,
                user_request=text,
                entities={"action": "analyze"}
            )

        if re.search(r"\b(?:create\s+(?:an?\s+)?(?:upgrade\s+)?plan|create\s+a\s+plan\s+to\s+improve|plan\s+self\s+upgrade|improve\s+your\s+intelligence)\b", lower):
            return Intent(
                type=IntentType.SELF_UPGRADE_PLAN,
                confidence=0.95,
                user_request=text,
                entities={"action": "plan"}
            )

        if re.search(r"\b(?:apply\s+(?:the\s+)?(?:approved\s+)?upgrade|apply\s+self\s+upgrade|perform\s+upgrade)\b", lower):
            return Intent(
                type=IntentType.SELF_UPGRADE_APPLY,
                confidence=0.95,
                user_request=text,
                entities={"action": "apply"},
                requires_confirmation=True
            )

        if re.search(r"\b(?:rollback\s+(?:the\s+)?upgrade|revert\s+(?:the\s+)?upgrade|undo\s+last\s+upgrade)\b", lower):
            return Intent(
                type=IntentType.SELF_ROLLBACK,
                confidence=0.95,
                user_request=text,
                entities={"action": "rollback"},
                requires_confirmation=True
            )

        # 0d. Knowledge Subsystem Intents (Stage 11 RAG)
        if re.search(r"\b(?:search|find|look\s+up)\s+(?:in\s+)?(?:my\s+)?(?:documents?|docs?|knowledge(?:\s+base)?|notes?)\s+(?:for\s+|about\s+)?(.+)$", lower):
            m = re.search(r"\b(?:search|find|look\s+up)\s+(?:in\s+)?(?:my\s+)?(?:documents?|docs?|knowledge(?:\s+base)?|notes?)\s+(?:for\s+|about\s+)?(.+)$", clean, re.IGNORECASE)
            query = m.group(1).strip().rstrip(".!?,") if m else clean
            # If the search specifically targets filesystem records/files (e.g. "tax records", "receipts"),
            # this is a filesystem search in Documents rather than conceptual RAG knowledge retrieval:
            if re.search(r"\b(?:tax\s+records?|records?|receipts?|invoices?|files?|spreadsheets?|\.[a-zA-Z0-9]+)\b", query, re.IGNORECASE):
                return Intent(
                    type=IntentType.FILE_OPERATION,
                    confidence=0.95,
                    user_request=text,
                    entities={
                        "tool": "search_files",
                        "parameters": {"query": query, "location": "documents"},
                        "requires_local_files": True,
                        "primary_goal": "local_file_search",
                        "sub_goals": ["search_local_files"],
                        "selected_tool": "search_files",
                        "rejected_tools": []
                    },
                    required_tools=["search_files"]
                )
            return Intent(
                type=IntentType.KNOWLEDGE_SEARCH,
                confidence=0.95,
                user_request=text,
                entities={"query": query},
                required_tools=["knowledge_search"]
            )

        if re.search(r"\b(?:what\s+do(?:es)?\s+(?:my\s+)?(?:documents?|docs?|knowledge(?:\s+base)?|notes?)\s+say\s+about\s+|ask\s+(?:my\s+)?(?:documents?|docs?|knowledge))\b", lower):
            m = re.search(r"\b(?:what\s+do(?:es)?\s+(?:my\s+)?(?:documents?|docs?|knowledge(?:\s+base)?|notes?)\s+say\s+about\s+|ask\s+(?:my\s+)?(?:documents?|docs?|knowledge(?:\s+base)?|notes?)\s+)(.+)$", clean, re.IGNORECASE)
            question = m.group(1).strip() if m else clean
            return Intent(
                type=IntentType.KNOWLEDGE_QUERY,
                confidence=0.95,
                user_request=text,
                entities={"question": question},
                required_tools=["knowledge_query"]
            )

        if re.search(r"\b(?:ingest\s+document|index\s+(?:the\s+)?(?:document|file)|add\s+to\s+knowledge)\b", lower):
            m = re.search(r"\b(?:ingest\s+document|index\s+(?:the\s+)?(?:document|file)|add\s+to\s+knowledge)\s+(.+)$", clean, re.IGNORECASE)
            path = m.group(1).strip() if m else ""
            return Intent(
                type=IntentType.KNOWLEDGE_INGEST,
                confidence=0.95,
                user_request=text,
                entities={"path": path},
                required_tools=["knowledge_ingest"]
            )

        # 1. Cancellation Intent
        if re.search(r"^(?:cancel\s+(?:that|it|this|my\s+current\s+video|the\s+video|my\s+current\s+task|task)|stop\s+(?:the\s+video|video|generation|task)|abort(?:\s+task)?)$", lower):
            return Intent(
                type=IntentType.CANCEL_TASK,
                confidence=1.0,
                user_request=text,
                entities={"target": "video" if "video" in lower else "active_task"}
            )

        # 2. Multi-Step Task Patterns (Image -> Video, Tool -> Tool, Image -> Video -> Memory)
        multi_step = self._check_multi_step(text, clean, ctx)
        if multi_step:
            return multi_step

        # 3. Image-to-Video Animation Intent (Standalone)
        # e.g. "turn that image into a video", "turn it into a video", "animate this image"
        if re.search(r"\b(?:turn\s+(?:that|the|this|it)?\s*(?:image|picture)?\s*into\s+(?:a\s+)?(?:cinematic\s+)?video|animate\s+(?:that|the|this|it|the\s+image|the\s+picture|it\b))\b", lower):
            prompt_match = re.search(r"\b(?:video\s+of|video\s+showing|video\s+with|prompt:)\s+(.+)$", clean, re.IGNORECASE)
            animation_prompt = prompt_match.group(1).strip() if prompt_match else (ctx.active_image_prompt or "cinematic animation")
            target_img_id = ctx_refs.get("image_id") or ctx.active_image_id
            return Intent(
                type=IntentType.IMAGE_TO_VIDEO,
                confidence=0.95,
                user_request=text,
                entities={
                    "image_id": target_img_id,
                    "prompt": animation_prompt
                },
                required_tools=["image_to_video"]
            )

        # 4. Standalone Video Generation Intent
        # e.g. "create a video of a red sports car", "generate a video of a rolling ball"
        if re.search(r"\b(?:create\s+(?:a\s+)?video|generate\s+(?:a\s+)?video|make\s+(?:a\s+)?video|produce\s+(?:a\s+)?video)\b", lower):
            match = re.search(r"\b(?:create|generate|make|produce)\s+(?:a\s+)?video\s+(?:of|showing|about|with)?\s+(.+)$", clean, re.IGNORECASE)
            prompt = match.group(1).strip() if match else clean
            return Intent(
                type=IntentType.VIDEO_GENERATION,
                confidence=0.95,
                user_request=text,
                entities={"prompt": prompt},
                required_tools=["text_to_video"]
            )

        # 4b. Vision & Image Understanding Intents (Stage 9)
        # OCR / Read text
        if re.search(r"\b(?:what\s+does\s+(?:this|that|the)\s+(?:screenshot|image|picture)\s+say|read\s+(?:the\s+)?text\s+in|extract\s+text\s+from|ocr\s+(?:this|that|the))\b", lower):
            is_active = bool(re.search(r"\b(?:that|the\s+last|the\s+recent|the\s+generated|that\s+image)\b", lower) or ctx.active_image_id)
            return Intent(
                type=IntentType.VISION_OCR,
                confidence=0.95,
                user_request=text,
                entities={"prompt": clean, "use_active": is_active, "image_id": ctx.active_image_id if is_active else None},
                required_tools=["vision_ocr"]
            )

        # Visual Scene Description
        if re.search(r"\b(?:describe\s+(?:this|that|the)\s+(?:image|picture)|describe\s+(?:the\s+)?main\s+buildings)\b", lower):
            is_active = bool(re.search(r"\b(?:that|the|active|generated)\b", lower) or ctx.active_image_id)
            return Intent(
                type=IntentType.VISION_DESCRIBE,
                confidence=0.95,
                user_request=text,
                entities={"prompt": clean, "use_active": is_active, "image_id": ctx.active_image_id if is_active else None},
                required_tools=["vision_describe"]
            )

        # Visual Question Answering
        if re.search(r"\b(?:is\s+there\s+(?:a|an|any)\s+.+\s+in\s+(?:this|that|the)\s+(?:image|picture)|what\s+do\s+you\s+see|what\s+is\s+in\s+(?:this|that|the)\s+(?:image|picture))\b", lower):
            is_active = bool(re.search(r"\b(?:that|the|active|generated)\b", lower) or ctx.active_image_id)
            return Intent(
                type=IntentType.VISION_QUESTION,
                confidence=0.95,
                user_request=text,
                entities={"prompt": clean, "question": clean, "use_active": is_active, "image_id": ctx.active_image_id if is_active else None},
                required_tools=["vision_question"]
            )

        # Image Analysis
        if re.search(r"\b(?:analyze\s+(?:that|this|the)\s+(?:image|picture)|analyze\s+the\s+image\s+i\s+just\s+generated|look\s+at\s+(?:this|that|the)\s+(?:image|picture)|examine\s+(?:this|that|the)\s+(?:image|picture))\b", lower):
            is_active = bool(re.search(r"\b(?:that|just\s+generated|generated|active|the)\b", lower) or ctx.active_image_id)
            return Intent(
                type=IntentType.VISION_ANALYZE,
                confidence=0.95,
                user_request=text,
                entities={"prompt": clean, "use_active": is_active, "image_id": ctx.active_image_id if is_active else None},
                required_tools=["vision_analyze"]
            )

        # 5. Image Generation & Editing Intents
        # 5a. Edit active image ("make it darker", "make it more cinematic")
        if (
            re.search(r"\b(?:make\s+it|turn\s+it|change\s+it|edit\s+(?:the|this|that)\s+image|update\s+(?:the|this|that)\s+image)\b", lower)
            and ctx.active_image_id
            and not re.search(r"\bvideo\b", lower)
        ):

            edit_match = re.search(r"\b(?:make\s+it|turn\s+it|change\s+it\s+to|edit\s+(?:the|this|that)\s+image\s+to\s+be|update\s+(?:the|this|that)\s+image\s+to\s+be)\s+(.+)$", clean, re.IGNORECASE)
            instruction = edit_match.group(1).strip() if edit_match else clean
            return Intent(
                type=IntentType.IMAGE_EDIT,
                confidence=0.9,
                user_request=text,
                entities={"instruction": instruction, "image_id": ctx.active_image_id},
                required_tools=["image_edit"]
            )

        # 5b. Regenerate image
        if re.search(r"\b(?:regenerate\s+(?:the\s+)?image|try\s+another\s+image|new\s+image\s+version|redo\s+(?:the\s+)?image)\b", lower):
            return Intent(
                type=IntentType.IMAGE_REGENERATE,
                confidence=0.95,
                user_request=text,
                entities={"image_id": ctx.active_image_id},
                required_tools=["image_regenerate"]
            )

        # 5c. Create new image
        if re.search(r"\b(?:create\s+(?:an?\s+)?image|generate\s+(?:an?\s+)?image|draw\s+(?:an?\s+)?|paint\s+(?:an?\s+)?|make\s+(?:an?\s+)?image)\b", lower) and not re.search(r"\bvideo\b", lower):
            match = re.search(r"\b(?:create|generate|draw|paint|make)\s+(?:an?\s+)?image\s+(?:of|showing|with|about)?\s+(.+)$", clean, re.IGNORECASE)
            prompt = match.group(1).strip() if match else clean
            return Intent(
                type=IntentType.IMAGE_GENERATION,
                confidence=0.95,
                user_request=text,
                entities={"prompt": prompt},
                required_tools=["image_generation"]
            )

        # 5d. Personalization & Proactive Intelligence (Stage 12)
        if re.search(r"^(?:enable\s+proactive\s+mode|turn\s+on\s+proactive\s+mode)$", lower):
            return Intent(
                type=IntentType.PROACTIVE_ENABLE,
                confidence=1.0,
                user_request=text,
                entities={"enable": True}
            )

        if re.search(r"^(?:disable\s+proactive\s+mode|turn\s+off\s+proactive\s+mode)$", lower):
            return Intent(
                type=IntentType.PROACTIVE_DISABLE,
                confidence=1.0,
                user_request=text,
                entities={"enable": False}
            )

        if re.search(r"\b(?:give\s+me|show|what\s+is|what's|generate)\s+(?:my\s+)?(?:morning\s+)?briefing\b", lower) or re.search(r"\bwhat\s+do\s+i\s+have\s+today\b", lower):
            return Intent(
                type=IntentType.DAILY_BRIEFING,
                confidence=0.95,
                user_request=text
            )

        if re.search(r"\b(?:evening\s+summary|end\s+of\s+day\s+summary)\b", lower):
            return Intent(
                type=IntentType.EVENING_SUMMARY,
                confidence=0.95,
                user_request=text
            )

        if re.search(r"\b(?:remind\s+me|schedule(?:\s+a)?\s+reminder|create(?:\s+a)?\s+reminder)\b", lower):
            return Intent(
                type=IntentType.REMINDER_CREATE,
                confidence=0.95,
                user_request=text,
                entities={"text": clean}
            )

        if re.search(r"\b(?:show\s+(?:my\s+)?reminders|what\s+are\s+my\s+reminders|list\s+reminders)\b", lower):
            return Intent(
                type=IntentType.REMINDER_LIST,
                confidence=0.95,
                user_request=text
            )

        if re.search(r"\b(?:cancel|delete)\s+(?:my\s+)?reminder\b", lower):
            target = re.sub(r"^(?:cancel|delete)\s+(?:my\s+)?reminder\s*", "", lower).strip()
            return Intent(
                type=IntentType.REMINDER_DELETE,
                confidence=0.95,
                user_request=text,
                entities={"target": target}
            )

        # 6. Memory Directives (Stage 4 integration)
        # 6a. Explicit Recall (Check before Remember to avoid matching questions containing 'remember')
        if re.search(r"\b(?:what\s+do\s+you\s+remember|recall\s+my|what\s+are\s+my\s+preferences|what\s+is\s+my\s+saved|do\s+you\s+remember)\b", lower):
            topic_match = re.search(r"\b(?:about|regarding|for)\s+(.+)$", clean, re.IGNORECASE)
            topic = topic_match.group(1).strip() if topic_match else ""
            return Intent(
                type=IntentType.MEMORY_RECALL,
                confidence=0.95,
                user_request=text,
                entities={"topic": topic},
                required_tools=["memory_recall"]
            )

        # 6b. Explicit Remember
        if re.search(r"\b(?:remember\s+that\b|please\s+remember\b|^remember\b|don'?t\s+forget\b|keep\s+in\s+mind\b)", lower):
            match = re.search(r"\b(?:remember\s+(?:that\s+)?|don'?t\s+forget\s+(?:that\s+)?|keep\s+in\s+mind\s+(?:that\s+)?)(.+)$", clean, re.IGNORECASE)
            fact = match.group(1).strip() if match else clean
            return Intent(
                type=IntentType.MEMORY_SAVE,
                confidence=0.95,
                user_request=text,
                entities={"fact": fact, "is_sensitive": is_sensitive_secret(fact)},
                required_tools=["memory_save"]
            )

        # 6c. Explicit Forget
        if re.search(r"\b(?:forget\s+(?:that\s+)?|forget\s+my\s+|delete\s+my\s+memory\s+about)\b", lower) and not re.search(r"\bclear\s+all\b", lower):
            match = re.search(r"\b(?:forget\s+(?:that\s+)?|forget\s+my\s+|delete\s+my\s+memory\s+about\s+)(.+)$", clean, re.IGNORECASE)
            pattern = match.group(1).strip() if match else clean
            return Intent(
                type=IntentType.MEMORY_FORGET,
                confidence=0.95,
                user_request=text,
                entities={"pattern": pattern},
                required_tools=["memory_forget"]
            )

        # 6d. Explicit Clear All Memories
        if re.search(r"\b(?:clear\s+(?:all\s+)?(?:my\s+)?memories|delete\s+all\s+(?:my\s+)?memories|wipe\s+(?:my\s+)?memory)\b", lower):
            return Intent(
                type=IntentType.MEMORY_CLEAR,
                confidence=0.95,
                user_request=text,
                entities={},
                requires_confirmation=True,
                required_tools=["memory_clear"]
            )

        # 7. System Information
        if re.search(r"\b(?:what\s+time\s+is\s+it|what\s+is\s+the\s+time|current\s+time|tell\s+me\s+the\s+time|what\s+is\s+today'?s\s+date|what\s+date\s+is\s+it)\b", lower):
            return Intent(
                type=IntentType.SYSTEM_INFORMATION,
                confidence=1.0,
                user_request=text,
                entities={"query": "time"},
                required_tools=["get_system_time"]
            )

        # 8. Windows System & Tool Actions
        tool_intent = self._check_tool_actions(clean, lower, ctx)
        if tool_intent:
            return tool_intent

        # 9. Help & Capabilities
        if re.search(r"^(?:help|what\s+can\s+you\s+do|show\s+(?:me\s+)?commands|capabilities)$", lower):
            return Intent(type=IntentType.HELP, confidence=1.0, user_request=text)

        # 10. General Chat & Questions
        if re.search(r"^(?:hello|hi|hey|good\s+morning|good\s+evening|good\s+afternoon|howdy)(?:\s+tony)?$", lower):
            return Intent(type=IntentType.CHAT, confidence=1.0, user_request=text)

        scope = analyze_target_scope(clean)
        if (
            clean.endswith("?")
            or re.search(r"^(?:what|who|where|when|why|how|explain|describe|tell\s+me\s+about)\b", lower)
            or re.search(r"^(?:find|search|lookup|look\s+up|recommend|suggest|check)\b", lower)
        ):
            rejected_tools = [{"tool": "search_files", "reason": scope.rejection_reason}] if scope and not scope.is_local_file else []
            return Intent(
                type=IntentType.QUESTION,
                confidence=0.85,
                user_request=text,
                entities={
                    "primary_goal": scope.primary_goal or "information_query",
                    "sub_goals": scope.sub_goals or ["answer_question"],
                    "requires_local_files": False,
                    "selected_tool": None,
                    "rejected_tools": rejected_tools
                }
            )

        return Intent(type=IntentType.CHAT, confidence=0.7, user_request=text)

    def _check_multi_step(self, original: str, clean: str, ctx: ConversationContext) -> Optional[Intent]:
        """Detect and structure multi-step commands joined by 'and', 'then', or commas."""
        lower = clean.lower()

        # Pattern A: "Create an image of X and turn it into a (cinematic) video"
        # Optional: "... and remember that I like this style"
        img_to_vid_chain = re.search(
            r"^(?:create|generate|draw|paint)\s+(?:an?\s+)?image\s+(?:of\s+)?(.+?)(?:,\s*|\s+)(?:and\s+turn\s+it\s+into\s+(?:a\s+)?(?:cinematic\s+)?video|turn\s+it\s+into\s+(?:a\s+)?(?:cinematic\s+)?video|and\s+make\s+(?:a\s+)?(?:cinematic\s+)?video\s+(?:from\s+it|of\s+it)|then\s+(?:turn\s+it\s+into\s+(?:a\s+)?video|make\s+a\s+video))(?:(?:,\s*|\s+)and\s+(?:remember|save)\s+(?:that\s+)?(.+?))?[.]?$",
            clean,
            re.IGNORECASE
        )
        if img_to_vid_chain:
            img_prompt = img_to_vid_chain.group(1).strip()
            mem_clause = img_to_vid_chain.group(2)
            sub_intents = [
                {"action": "image_generation", "prompt": img_prompt},
                {"action": "image_to_video", "prompt": f"cinematic video of {img_prompt}"}
            ]
            if mem_clause:
                sub_intents.append({"action": "memory_save", "fact": mem_clause.strip()})

            return Intent(
                type=IntentType.MULTI_STEP_TASK,
                confidence=0.98,
                user_request=original,
                entities={"sub_actions": sub_intents},
                sub_intents=sub_intents,
                required_tools=["image_generation", "image_to_video"] + (["memory_save"] if mem_clause else [])
            )

        # Pattern B: "Increase the volume and open YouTube"
        vol_and_web = re.search(
            r"^(?:increase\s+(?:the\s+)?volume|volume\s+up|turn\s+up\s+the\s+volume)\s+(?:and|then)\s+(?:open|launch|go\s+to)\s+(.+)$",
            clean,
            re.IGNORECASE
        )
        if vol_and_web:
            target_site = vol_and_web.group(1).strip()
            sub_intents = [
                {"action": "tool_execution", "tool": "volume_up", "parameters": {"steps": 2}},
                {"action": "tool_execution", "tool": "open_website", "parameters": {"target": target_site, "url": target_site}}
            ]
            return Intent(
                type=IntentType.MULTI_STEP_TASK,
                confidence=0.95,
                user_request=original,
                entities={"sub_actions": sub_intents},
                sub_intents=sub_intents,
                required_tools=["volume_up", "open_website"]
            )

        # Pattern C: "Create a folder called X and open it"
        create_and_open = re.search(
            r"^(?:create|make)\s+(?:a\s+)?folder\s+(?:called|named)\s+([a-zA-Z0-9_\-\s]+?)\s+(?:and|then)\s+(?:open|launch)\s+it$",
            clean,
            re.IGNORECASE
        )
        if create_and_open:
            folder_name = create_and_open.group(1).strip()
            sub_intents = [
                {"action": "tool_execution", "tool": "create_folder", "parameters": {"folder_name": folder_name}},
                {"action": "tool_execution", "tool": "open_folder", "parameters": {"folder_path": f"$step_1.result.path"}}
            ]
            return Intent(
                type=IntentType.MULTI_STEP_TASK,
                confidence=0.95,
                user_request=original,
                entities={"sub_actions": sub_intents},
                sub_intents=sub_intents,
                required_tools=["create_folder", "open_folder"]
            )

        # Pattern C2: "Create a folder called X and delete it" / "create a folder A then delete it"
        create_and_delete = re.search(
            r"^(?:create|make)\s+(?:a\s+)?folder\s+(?:called\s+|named\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+(?:on|in|at)\s+(?:my\s+)?([a-zA-Z0-9_\-\s]+?))?\s+(?:and|then)\s+(?:delete|remove|erase|destroy|trash|wipe)\s+it$",
            clean,
            re.IGNORECASE
        )
        if create_and_delete:
            folder_name = create_and_delete.group(1).strip()
            loc = create_and_delete.group(2).strip() if create_and_delete.group(2) else "Desktop"
            sub_intents = [
                {"action": "tool_execution", "tool": "create_folder", "parameters": {"name": folder_name, "folder_name": folder_name, "location": loc}},
                {"action": "tool_execution", "tool": "delete_folder", "parameters": {"target": f"{loc}/{folder_name}", "folder_path": f"{loc}/{folder_name}"}, "requires_confirmation": True}
            ]
            return Intent(
                type=IntentType.MULTI_STEP_TASK,
                confidence=0.95,
                user_request=original,
                entities={"sub_actions": sub_intents},
                sub_intents=sub_intents,
                requires_confirmation=True,
                required_tools=["create_folder", "delete_folder"]
            )

        # Pattern D: "Open my TONY AI project folder and find the latest video"
        open_and_find = re.search(
            r"^open\s+(?:my\s+)?(?:tony\s+ai\s+)?(?:project\s+)?folder\s+(?:and|then)\s+(?:find|search\s+for)\s+(?:the\s+)?(?:latest\s+)?(video|image|file|mp4|png)$",
            clean,
            re.IGNORECASE
        )
        if open_and_find:
            query = open_and_find.group(1).strip()
            sub_intents = [
                {"action": "tool_execution", "tool": "open_folder", "parameters": {"folder_path": "."}},
                {"action": "tool_execution", "tool": "search_files", "parameters": {"query": f"*.{query}" if query in ("mp4", "png") else "*.mp4"}}
            ]
            return Intent(
                type=IntentType.MULTI_STEP_TASK,
                confidence=0.95,
                user_request=original,
                entities={"sub_actions": sub_intents},
                sub_intents=sub_intents,
                required_tools=["open_folder", "search_files"]
            )

        # Pattern E: General Multi-Goal / Compound Natural Language Requests
        scope = analyze_target_scope(clean)
        if scope.is_compound and len(scope.clauses) > 1:
            sub_intents = []
            req_tools = []
            for i, clause in enumerate(scope.clauses):
                clause_scope = analyze_target_scope(clause)
                clause_lower = clause.lower().strip()
                if clause_scope.is_local_file and clause_scope.query:
                    q = clause_scope.query
                    sub_intents.append({
                        "action": "tool_execution",
                        "tool": "search_files",
                        "parameters": {"query": q, "location": clause_scope.location},
                        "description": f"Search local files for {q}"
                    })
                    req_tools.append("search_files")
                elif i == 0:
                    sub_intents.append({
                        "action": "research",
                        "topic": clause,
                        "description": f"Research: {clause}"
                    })
                elif "compare" in clause_lower:
                    sub_intents.append({
                        "action": "comparison",
                        "instruction": clause,
                        "description": f"Compare options: {clause}"
                    })
                elif any(k in clause_lower for k in ("plan", "study", "learn", "schedule")):
                    sub_intents.append({
                        "action": "planning",
                        "instruction": clause,
                        "description": f"Formulate plan: {clause}"
                    })
                elif "summarize" in clause_lower:
                    sub_intents.append({
                        "action": "analysis",
                        "instruction": clause,
                        "description": f"Summarize content: {clause}"
                    })
                elif "explain" in clause_lower:
                    sub_intents.append({
                        "action": "analysis",
                        "instruction": clause,
                        "description": f"Explain content: {clause}"
                    })
                else:
                    sub_intents.append({
                        "action": "chat",
                        "query": clause,
                        "description": clause
                    })

            # Structured diagnostic information
            entities = {
                "request_type": "multi_step",
                "primary_goal": scope.primary_goal or "multi_goal_task",
                "sub_goals": scope.sub_goals,
                "sub_actions": sub_intents,
                "requires_local_files": scope.is_local_file,
                "selected_tool": req_tools[0] if req_tools else None,
                "rejected_tools": [{"tool": "search_files", "reason": scope.rejection_reason}] if not scope.is_local_file else []
            }
            logger.info(
                f"Multi-step Intent: primary_goal={entities['primary_goal']}, "
                f"sub_goals={entities['sub_goals']}, requires_local_files={entities['requires_local_files']}"
            )
            return Intent(
                type=IntentType.MULTI_STEP_TASK,
                confidence=0.96,
                user_request=original,
                entities=entities,
                sub_intents=sub_intents,
                required_tools=list(dict.fromkeys(req_tools))
            )

        return None

    def _check_tool_actions(self, clean: str, lower: str, ctx: ConversationContext) -> Optional[Intent]:
        """Inspect and parse single Windows and filesystem tools."""
        # 1. Volume
        if re.search(r"\b(?:increase\s+(?:the\s+)?volume|volume\s+up|make\s+it\s+louder|louder)\b", lower):
            match = re.search(r"\b(?:by\s+)?(\d+)\b", lower)
            steps = int(match.group(1)) if match else 2
            return Intent(
                type=IntentType.WINDOWS_ACTION,
                confidence=0.95,
                user_request=clean,
                entities={"tool": "volume_up", "parameters": {"steps": steps}},
                required_tools=["volume_up"]
            )

        if re.search(r"\b(?:decrease\s+(?:the\s+)?volume|volume\s+down|lower\s+(?:the\s+)?volume|quieter)\b", lower):
            match = re.search(r"\b(?:by\s+)?(\d+)\b", lower)
            steps = int(match.group(1)) if match else 2
            return Intent(
                type=IntentType.WINDOWS_ACTION,
                confidence=0.95,
                user_request=clean,
                entities={"tool": "volume_down", "parameters": {"steps": steps}},
                required_tools=["volume_down"]
            )

        if re.search(r"^(?:mute(?:\s+(?:the\s+)?volume)?|silence\s+audio)$", lower):
            return Intent(
                type=IntentType.WINDOWS_ACTION,
                confidence=0.95,
                user_request=clean,
                entities={"tool": "volume_mute", "parameters": {}},
                required_tools=["volume_mute"]
            )

        if re.search(r"^(?:unmute(?:\s+(?:the\s+)?volume)?)$", lower):
            return Intent(
                type=IntentType.WINDOWS_ACTION,
                confidence=0.95,
                user_request=clean,
                entities={"tool": "volume_unmute", "parameters": {}},
                required_tools=["volume_unmute"]
            )

        # 2. Media
        if re.search(r"\b(?:play\s+pause|pause\s+music|resume\s+music|play\s+music)\b", lower):
            return Intent(
                type=IntentType.WINDOWS_ACTION,
                confidence=0.95,
                user_request=clean,
                entities={"tool": "play_pause", "parameters": {}},
                required_tools=["play_pause"]
            )

        # 3. Website
        open_web_match = re.search(r"^(?:open|go\s+to|launch|browse\s+to)\s+(?:website\s+|site\s+)?([a-zA-Z0-9_\-\.\:\/]+)$", clean, re.IGNORECASE)
        if open_web_match:
            target = open_web_match.group(1).strip()
            # If target looks like a website or known service
            if target.lower() in ("youtube", "google", "github", "reddit", "twitter") or any(target.endswith(tld) for tld in [".com", ".org", ".net", ".io", ".dev", ".ai"]):
                return Intent(
                    type=IntentType.WINDOWS_ACTION,
                    confidence=0.95,
                    user_request=clean,
                    entities={"tool": "open_website", "parameters": {"target": target, "url": target}},
                    required_tools=["open_website"]
                )

        # 4. Applications
        open_app_match = re.search(r"^(?:open|launch|start|run)\s+(?:app\s+|application\s+)?([a-zA-Z0-9_\-\s]+?)$", clean, re.IGNORECASE)
        if open_app_match:
            app_name = open_app_match.group(1).strip()
            # If not website or folder
            if not re.search(r"\b(?:folder|directory|website)\b", lower):
                return Intent(
                    type=IntentType.WINDOWS_ACTION,
                    confidence=0.9,
                    user_request=clean,
                    entities={"tool": "open_application", "parameters": {"application": app_name}},
                    required_tools=["open_application"]
                )

        # 5. Folders
        create_folder_match = re.search(r"^(?:create|make)\s+(?:a\s+)?folder\s+(?:called|named)?\s*(.+)$", clean, re.IGNORECASE)
        if create_folder_match:
            fname = create_folder_match.group(1).strip().strip("'\"")
            return Intent(
                type=IntentType.FILE_OPERATION,
                confidence=0.95,
                user_request=clean,
                entities={"tool": "create_folder", "parameters": {"name": fname, "folder_name": fname}},
                required_tools=["create_folder"]
            )

        if re.search(r"\b(?:open|show)\s+(?:my\s+)?(?:tony\s+ai\s+)?project\s+folder\b", lower):
            return Intent(
                type=IntentType.FILE_OPERATION,
                confidence=0.95,
                user_request=clean,
                entities={"tool": "open_folder", "parameters": {"target": "TONY_AI", "folder_path": "TONY_AI"}},
                required_tools=["open_folder"]
            )

        if re.search(r"\b(?:delete|remove)\s+(?:my\s+)?(?:tony\s+ai\s+)?project\s+folder\b", lower):
            return Intent(
                type=IntentType.FILE_OPERATION,
                confidence=0.95,
                user_request=clean,
                entities={"tool": "delete_folder", "parameters": {"target": "TONY_AI", "folder_path": "TONY_AI"}},
                requires_confirmation=True,
                required_tools=["delete_folder"]
            )

        open_folder_match = re.search(r"^(?:open|show)\s+(?:the\s+|my\s+)?folder\s+(.+)$", clean, re.IGNORECASE)
        if open_folder_match:
            fpath = open_folder_match.group(1).strip().strip("'\"")
            return Intent(
                type=IntentType.FILE_OPERATION,
                confidence=0.95,
                user_request=clean,
                entities={"tool": "open_folder", "parameters": {"target": fpath, "folder_path": fpath}},
                required_tools=["open_folder"]
            )

        delete_folder_match = re.search(r"^(?:delete|remove)\s+(?:the\s+)?folder\s+(?:called|named)?\s*(.+)$", clean, re.IGNORECASE)
        if delete_folder_match:
            fname = delete_folder_match.group(1).strip().strip("'\"")
            return Intent(
                type=IntentType.FILE_OPERATION,
                confidence=0.95,
                user_request=clean,
                entities={"tool": "delete_folder", "parameters": {"target": fname, "folder_path": fname}},
                requires_confirmation=True,  # HIGH-risk action!
                required_tools=["delete_folder"]
            )

        # 6. Files
        delete_file_match = re.search(r"^(?:delete|remove)\s+(?:the\s+)?file\s+(?:called|named)?\s*(.+)$", clean, re.IGNORECASE)
        if delete_file_match:
            fname = delete_file_match.group(1).strip().strip("'\"")
            return Intent(
                type=IntentType.FILE_OPERATION,
                confidence=0.95,
                user_request=clean,
                entities={"tool": "delete_file", "parameters": {"file_path": fname}},
                requires_confirmation=True,  # HIGH-risk action!
                required_tools=["delete_file"]
            )

        # 6b. Search Files (requires positive evidence of local storage target)
        scope = analyze_target_scope(clean)
        if scope.is_local_file and not scope.is_compound and scope.query:
            query = scope.query.strip().strip("'\"")
            return Intent(
                type=IntentType.FILE_OPERATION,
                confidence=0.9,
                user_request=clean,
                entities={
                    "tool": "search_files",
                    "parameters": {"query": query, "location": scope.location},
                    "requires_local_files": True,
                    "primary_goal": "local_file_search",
                    "sub_goals": ["search_local_files"],
                    "selected_tool": "search_files",
                    "rejected_tools": []
                },
                required_tools=["search_files"]
            )

        return None
