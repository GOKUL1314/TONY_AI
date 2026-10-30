"""
Goal Decomposition and Multi-Step Planner for TONY AI Agent Subsystem (Stage 10).
Converts complex natural language goals into structured AgentPlans with explicit
dependencies, risk classification, and dynamic parameter interpolation.
"""
import re
import uuid
import logging
from typing import Optional, List, Dict, Any

from agent.models import (
    AgentPlan,
    AgentStep,
    AgentStepStatus,
    AgentRiskLevel,
    AgentTaskStatus
)
from agent.policies import AgentSecurityPolicy
from agent.validator import AgentValidator
from intelligence.intent import IntentEngine
from intelligence.models import Intent, IntentType
from intelligence.context import ConversationContext

logger = logging.getLogger("tony.agent.planner")


class AgentPlanner:
    """Plans multi-step agent actions from natural language goals."""

    def __init__(self, tool_registry=None):
        self.tool_registry = tool_registry
        self.intent_engine = IntentEngine(tool_registry=tool_registry)

    def plan(self, user_goal: str, context: Optional[ConversationContext] = None) -> AgentPlan:
        """
        Synthesize a structured AgentPlan from a user goal string.
        """
        AgentValidator.validate_user_request(user_goal)
        ctx = context or ConversationContext()
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        plan = AgentPlan(plan_id=plan_id, user_goal=user_goal, status=AgentTaskStatus.PLANNING)

        clean = self.intent_engine.clean_text(user_goal)
        lower = clean.lower()

        # ----------------------------------------------------------------------
        # Pattern 1: Multi-Modal Quad Chain
        # e.g. "create a futuristic Hyderabad image, analyze it, turn it into a short video, and save the results in a folder called Hyderabad Project"
        # ----------------------------------------------------------------------
        quad_match = re.search(
            r"(?:create|generate)\s+(?:an?\s+)?(.+?)\s+image[,\s]+(?:then\s+)?analyze\s+it[,\s]+(?:then\s+)?(?:turn\s+it\s+into\s+a\s+(?:short\s+)?video|make\s+a\s+video)[,\s]+(?:and\s+)?(?:save\s+(?:the\s+)?results?\s+in\s+(?:a\s+)?folder\s+called|put\s+it\s+in\s+(?:a\s+)?folder\s+called)\s+([a-zA-Z0-9_\-\s]+)",
            lower
        )
        if quad_match:
            img_prompt = quad_match.group(1).strip()
            folder_name = quad_match.group(2).strip()

            step1 = AgentStep(
                step_id="step_1",
                description=f"Generate image: {img_prompt}",
                action_type="image_generation",
                arguments={"prompt": img_prompt},
                dependencies=[]
            )
            step2 = AgentStep(
                step_id="step_2",
                description="Analyze generated image using vision model",
                action_type="vision_analyze",
                arguments={"image_id": "$step_1.result.image_id", "use_active": True},
                dependencies=["step_1"]
            )
            step3 = AgentStep(
                step_id="step_3",
                description="Synthesize video from generated image",
                action_type="image_to_video",
                arguments={"image_id": "$step_1.result.image_id", "prompt": f"cinematic animation of {img_prompt}"},
                dependencies=["step_1"]
            )
            step4 = AgentStep(
                step_id="step_4",
                description=f"Create folder: {folder_name}",
                action_type="tool_execution",
                arguments={"tool": "create_folder", "parameters": {"folder_name": folder_name}},
                dependencies=[]
            )
            plan.steps = [step1, step2, step3, step4]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # ----------------------------------------------------------------------
        # Pattern 2: Folder + Image + Vision + Video
        # e.g. "create a folder called AI Projects, generate an image of a futuristic Hyderabad city, analyze the image, and make a video from it"
        # ----------------------------------------------------------------------
        folder_chain = re.search(
            r"(?:create\s+(?:a\s+)?folder\s+called\s+([a-zA-Z0-9_\-\s]+?))[,\s]+(?:generate|create)\s+(?:an?\s+)?image\s+(?:of\s+)?(.+?)[,\s]+(?:analyze\s+(?:the\s+)?image)[,\s]+(?:and\s+)?(?:make|generate|turn\s+it\s+into)\s+(?:a\s+)?video",
            lower
        )
        if folder_chain:
            folder_name = folder_chain.group(1).strip()
            img_prompt = folder_chain.group(2).strip()

            step1 = AgentStep(
                step_id="step_1",
                description=f"Create folder: {folder_name}",
                action_type="tool_execution",
                arguments={"tool": "create_folder", "parameters": {"folder_name": folder_name}},
                dependencies=[]
            )
            step2 = AgentStep(
                step_id="step_2",
                description=f"Generate image: {img_prompt}",
                action_type="image_generation",
                arguments={"prompt": img_prompt},
                dependencies=[]
            )
            step3 = AgentStep(
                step_id="step_3",
                description="Analyze generated image using vision model",
                action_type="vision_analyze",
                arguments={"image_id": "$step_2.result.image_id", "use_active": True},
                dependencies=["step_2"]
            )
            step4 = AgentStep(
                step_id="step_4",
                description="Generate video from generated image",
                action_type="image_to_video",
                arguments={"image_id": "$step_2.result.image_id", "prompt": f"cinematic video of {img_prompt}"},
                dependencies=["step_2"]
            )
            plan.steps = [step1, step2, step3, step4]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # ----------------------------------------------------------------------
        # Pattern 2.5: Image + Vision + Video
        # e.g. "create a futuristic car image, analyze it, and turn it into a short video"
        # ----------------------------------------------------------------------
        tri_match = re.search(
            r"(?:create|generate)\s+(?:an?\s+)?(.+?)\s+image[,\s]+(?:then\s+)?(?:analyze|examine|describe)\s+it[,\s]+(?:and\s+)?(?:then\s+)?(?:turn\s+it\s+into\s+a\s+(?:short\s+)?video|make\s+a\s+video|animate\s+it)",
            lower
        )
        if not tri_match:
            tri_match = re.search(
                r"(?:create|generate)\s+(?:an?\s+)?image\s+(?:of\s+)?(.+?)[,\s]+(?:then\s+)?(?:analyze|examine|describe)\s+it[,\s]+(?:and\s+)?(?:then\s+)?(?:turn\s+it\s+into\s+a\s+(?:short\s+)?video|make\s+a\s+video|animate\s+it)",
                lower
            )
        if tri_match:
            img_prompt = tri_match.group(1).strip()
            step1 = AgentStep(
                step_id="step_1",
                description=f"Generate image: {img_prompt}",
                action_type="image_generation",
                arguments={"prompt": img_prompt},
                dependencies=[]
            )
            step2 = AgentStep(
                step_id="step_2",
                description="Analyze generated image using vision model",
                action_type="vision_analyze",
                arguments={"image_id": "$step_1.result.image_id", "use_active": True},
                dependencies=["step_1"]
            )
            step3 = AgentStep(
                step_id="step_3",
                description="Synthesize video from generated image",
                action_type="image_to_video",
                arguments={"image_id": "$step_1.result.image_id", "prompt": f"cinematic video of {img_prompt}"},
                dependencies=["step_1"]
            )
            plan.steps = [step1, step2, step3]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # ----------------------------------------------------------------------
        # Pattern 3: Image + Vision
        # e.g. "create an image of a futuristic Hyderabad skyline and analyze it"
        # ----------------------------------------------------------------------
        img_vis_match = re.search(
            r"^(?:create|generate)\s+(?:an?\s+)?image\s+(?:of\s+)?(.+?)\s+(?:and|then)\s+(?:analyze|examine|describe)\s+it$",
            lower
        )
        if img_vis_match:
            img_prompt = img_vis_match.group(1).strip()
            step1 = AgentStep(
                step_id="step_1",
                description=f"Generate image: {img_prompt}",
                action_type="image_generation",
                arguments={"prompt": img_prompt},
                dependencies=[]
            )
            step2 = AgentStep(
                step_id="step_2",
                description="Analyze generated image using vision model",
                action_type="vision_analyze",
                arguments={"image_id": "$step_1.result.image_id", "use_active": True},
                dependencies=["step_1"]
            )
            plan.steps = [step1, step2]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # ----------------------------------------------------------------------
        # Pattern 4: Image + Video
        # e.g. "create an image of a futuristic Hyderabad skyline and turn it into a short video"
        # ----------------------------------------------------------------------
        img_vid_match = re.search(
            r"^(?:create|generate)\s+(?:an?\s+)?image\s+(?:of\s+)?(.+?)\s+(?:and|then)\s+(?:turn\s+it\s+into\s+a\s+(?:short\s+)?video|make\s+a\s+video|animate\s+it)$",
            lower
        )
        if img_vid_match:
            img_prompt = img_vid_match.group(1).strip()
            step1 = AgentStep(
                step_id="step_1",
                description=f"Generate image: {img_prompt}",
                action_type="image_generation",
                arguments={"prompt": img_prompt},
                dependencies=[]
            )
            step2 = AgentStep(
                step_id="step_2",
                description="Synthesize video from generated image",
                action_type="image_to_video",
                arguments={"image_id": "$step_1.result.image_id", "prompt": f"cinematic video of {img_prompt}"},
                dependencies=["step_1"]
            )
            plan.steps = [step1, step2]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # ----------------------------------------------------------------------
        # Pattern 5: Contextual Follow-Up
        # e.g. "put the image there", "save the image in that folder"
        # ----------------------------------------------------------------------
        if re.search(r"\b(?:put\s+(?:the\s+)?image\s+there|save\s+(?:the\s+)?image\s+in\s+that\s+folder)\b", lower):
            if ctx.active_image_path and ctx.active_folder_path:
                step1 = AgentStep(
                    step_id="step_1",
                    description=f"Copy active image to {ctx.active_folder_path}",
                    action_type="tool_execution",
                    arguments={
                        "tool": "copy_file",
                        "parameters": {
                            "source": ctx.active_image_path,
                            "destination": ctx.active_folder_path
                        }
                    },
                    dependencies=[]
                )
                plan.steps = [step1]
                self._apply_policies(plan)
                AgentValidator.validate_plan(plan)
                plan.status = AgentTaskStatus.QUEUED
                return plan

        # ----------------------------------------------------------------------
        # Pattern 6: Knowledge Base Operations (Stage 11)
        # ----------------------------------------------------------------------
        # Ingest document
        ingest_m = re.search(r"^(?:ingest|index)\s+(?:document|file|doc)?\s*([^\s].+?)(?:\s+into\s+knowledge(?:\s+base)?)?$", lower)
        if ingest_m:
            path_val = ingest_m.group(1).strip().strip("'\"")
            step1 = AgentStep(
                step_id="step_1",
                description=f"Ingest document into knowledge base: {path_val}",
                action_type="knowledge_ingest",
                arguments={"file_path": path_val},
                dependencies=[]
            )
            plan.steps = [step1]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # Search documents
        search_m = re.search(r"^(?:search|find|look\s+up)\s+(?:in\s+)?(?:my\s+)?(?:documents?|docs?|knowledge(?:\s+base)?|notes?)\s+(?:for\s+|about\s+)?(.+)$", lower)
        if search_m:
            query_val = search_m.group(1).strip()
            step1 = AgentStep(
                step_id="step_1",
                description=f"Search knowledge documents: {query_val}",
                action_type="knowledge_search",
                arguments={"query": query_val},
                dependencies=[]
            )
            plan.steps = [step1]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # Ask / Query documents
        ask_m = re.search(r"^(?:what\s+do(?:es)?\s+(?:my\s+)?(?:documents?|docs?|knowledge(?:\s+base)?|notes?)\s+say\s+about\s+|ask\s+(?:my\s+)?(?:documents?|docs?|knowledge(?:\s+base)?)\s+)(.+)$", lower)
        if ask_m:
            question_val = ask_m.group(1).strip()
            step1 = AgentStep(
                step_id="step_1",
                description=f"Query knowledge base: {question_val}",
                action_type="knowledge_query",
                arguments={"question": question_val},
                dependencies=[]
            )
            plan.steps = [step1]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # Delete document
        del_m = re.search(r"^(?:delete|remove)\s+(?:document|doc)\s+([a-zA-Z0-9_\-\.]+)(?:\s+from\s+knowledge(?:\s+base)?)?$", lower)
        if del_m:
            doc_id = del_m.group(1).strip()
            step1 = AgentStep(
                step_id="step_1",
                description=f"Delete document from knowledge base: {doc_id}",
                action_type="knowledge_delete",
                arguments={"document_id": doc_id},
                dependencies=[]
            )
            plan.steps = [step1]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # ----------------------------------------------------------------------
        # Pattern 8: Reminder Create (Stage 12)
        # e.g. "remind me tomorrow at 9 AM to study Python", "every day at 9 AM remind me to study"
        # ----------------------------------------------------------------------
        rem_m = re.search(r"^(?:remind\s+me|schedule(?:\s+a)?\s+reminder|create(?:\s+a)?\s+reminder|every\s+(?:day|weekday|\w+day)\s+(?:at\s+)?\d+.*remind\s+me)\s+(.+)$", lower)
        if rem_m or (lower.startswith("remind me ") or "remind me to " in lower):
            step1 = AgentStep(
                step_id="step_1",
                description=f"Schedule reminder: {clean}",
                action_type="reminder_create",
                arguments={"text": clean},
                dependencies=[]
            )
            plan.steps = [step1]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # ----------------------------------------------------------------------
        # Pattern 9: Reminder List (Stage 12)
        # e.g. "show my reminders", "what are my reminders", "list reminders"
        # ----------------------------------------------------------------------
        rem_list_m = re.search(r"^(?:show|list|what\s+are)\s+(?:all\s+)?(?:my\s+)?reminders?$", lower)
        if rem_list_m:
            step1 = AgentStep(
                step_id="step_1",
                description="List all scheduled reminders",
                action_type="reminder_list",
                arguments={},
                dependencies=[]
            )
            plan.steps = [step1]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # ----------------------------------------------------------------------
        # Pattern 10: Reminder Cancel / Delete (Stage 12)
        # e.g. "cancel my Python reminder", "delete reminder rem_123"
        # ----------------------------------------------------------------------
        rem_del_m = re.search(r"^(?:cancel|delete|remove)\s+(?:my\s+)?(?:scheduled\s+)?reminder\s*(.*)$", lower)
        if rem_del_m and not "document" in lower:
            target = rem_del_m.group(1).strip()
            step1 = AgentStep(
                step_id="step_1",
                description=f"Cancel reminder: {target or 'specified'}",
                action_type="reminder_delete",
                arguments={"target": target},
                dependencies=[]
            )
            plan.steps = [step1]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # ----------------------------------------------------------------------
        # Pattern 11: Morning Briefing & Daily Status (Stage 12)
        # e.g. "give me my morning briefing", "what's my morning briefing", "what do I have today"
        # ----------------------------------------------------------------------
        brief_m = re.search(r"^(?:(?:give\s+me|show|what\s+is|generate)\s+(?:my\s+)?(?:morning\s+)?briefing|what\s+do\s+i\s+have\s+today\??)$", lower)
        if brief_m:
            step1 = AgentStep(
                step_id="step_1",
                description="Generate daily morning briefing",
                action_type="briefing_generate",
                arguments={},
                dependencies=[]
            )
            plan.steps = [step1]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # ----------------------------------------------------------------------
        # Pattern 12: Proactive Mode Toggle (Stage 12)
        # e.g. "enable proactive mode", "disable proactive mode"
        # ----------------------------------------------------------------------
        pro_m = re.search(r"^(enable|disable)\s+proactive\s+mode$", lower)
        if pro_m:
            enable_flag = (pro_m.group(1) == "enable")
            step1 = AgentStep(
                step_id="step_1",
                description=f"{'Enable' if enable_flag else 'Disable'} proactive mode",
                action_type="proactive_toggle",
                arguments={"enable": enable_flag},
                dependencies=[]
            )
            plan.steps = [step1]
            self._apply_policies(plan)
            AgentValidator.validate_plan(plan)
            plan.status = AgentTaskStatus.QUEUED
            return plan

        # ----------------------------------------------------------------------
        # Pattern 7: Single-Intent / Core JARVIS Decomposition
        # Fall back to IntentEngine classification
        # ----------------------------------------------------------------------
        intent: Intent = self.intent_engine.detect_intent(clean, context=ctx)
        plan = self._build_from_intent(plan, intent, clean, ctx)
        self._apply_policies(plan)
        AgentValidator.validate_plan(plan)
        plan.status = AgentTaskStatus.QUEUED
        return plan

    def _build_from_intent(self, plan: AgentPlan, intent: Intent, clean: str, ctx: ConversationContext) -> AgentPlan:
        """Translate classified Intent into AgentStep(s)."""
        t = intent.type

        # Multi-step intent from intent engine
        if t == IntentType.MULTI_STEP_TASK and intent.sub_intents:
            for idx, sub in enumerate(intent.sub_intents):
                step_id = f"step_{idx+1}"
                act = sub.get("action", "")
                deps = [f"step_{idx}"] if idx > 0 and act in ("image_to_video", "vision_analyze", "open_folder") else []

                if act == "image_generation":
                    plan.steps.append(AgentStep(
                        step_id=step_id,
                        description=f"Generate image: {sub.get('prompt')}",
                        action_type="image_generation",
                        arguments={"prompt": sub.get("prompt")},
                        dependencies=deps
                    ))
                elif act == "image_to_video":
                    plan.steps.append(AgentStep(
                        step_id=step_id,
                        description=f"Animate into video: {sub.get('prompt')}",
                        action_type="image_to_video",
                        arguments={"image_id": "$step_1.result.image_id", "prompt": sub.get("prompt")},
                        dependencies=deps
                    ))
                elif act == "tool_execution":
                    plan.steps.append(AgentStep(
                        step_id=step_id,
                        description=f"Tool: {sub.get('tool')}",
                        action_type="tool_execution",
                        arguments={"tool": sub.get("tool"), "parameters": sub.get("parameters", {})},
                        dependencies=deps
                    ))
                elif act == "memory_save":
                    plan.steps.append(AgentStep(
                        step_id=step_id,
                        description=f"Save memory: {sub.get('fact')}",
                        action_type="memory_save",
                        arguments={"fact": sub.get("fact")},
                        dependencies=deps
                    ))
            return plan

        # Image Generation
        if t == IntentType.IMAGE_GENERATION:
            plan.steps.append(AgentStep(
                step_id="step_1",
                description=f"Generate image: {intent.entities.get('prompt')}",
                action_type="image_generation",
                arguments={"prompt": intent.entities.get("prompt")}
            ))
            return plan

        # Vision Intents
        if t in (IntentType.VISION_ANALYZE, IntentType.VISION_DESCRIBE, IntentType.VISION_QUESTION, IntentType.VISION_OCR):
            action_map = {
                IntentType.VISION_ANALYZE: "vision_analyze",
                IntentType.VISION_DESCRIBE: "vision_describe",
                IntentType.VISION_QUESTION: "vision_question",
                IntentType.VISION_OCR: "vision_ocr"
            }
            plan.steps.append(AgentStep(
                step_id="step_1",
                description=f"Vision task: {intent.entities.get('prompt', 'analyze image')}",
                action_type=action_map[t],
                arguments={
                    "prompt": intent.entities.get("prompt", ""),
                    "image_id": intent.entities.get("image_id") or (ctx.active_image_id if intent.entities.get("use_active") else None),
                    "use_active": intent.entities.get("use_active", False)
                }
            ))
            return plan

        # Tool Execution
        if t in (IntentType.WINDOWS_ACTION, IntentType.FILE_OPERATION, IntentType.SYSTEM_INFORMATION):
            tool_name = intent.entities.get("tool")
            params = intent.entities.get("parameters", {})
            if t == IntentType.SYSTEM_INFORMATION and not tool_name:
                tool_name = "get_system_time"
            plan.steps.append(AgentStep(
                step_id="step_1",
                description=f"Execute tool: {tool_name}",
                action_type="tool_execution",
                arguments={"tool": tool_name, "parameters": params}
            ))
            return plan

        # Video Generation
        if t == IntentType.VIDEO_GENERATION:
            plan.steps.append(AgentStep(
                step_id="step_1",
                description=f"Generate video: {intent.entities.get('prompt')}",
                action_type="text_to_video",
                arguments={"prompt": intent.entities.get("prompt")}
            ))
            return plan

        # Image-to-Video
        if t == IntentType.IMAGE_TO_VIDEO:
            plan.steps.append(AgentStep(
                step_id="step_1",
                description=f"Animate image: {intent.entities.get('prompt')}",
                action_type="image_to_video",
                arguments={
                    "image_id": intent.entities.get("image_id") or ctx.active_image_id,
                    "prompt": intent.entities.get("prompt")
                }
            ))
            return plan

        # Memory Operations
        if t == IntentType.MEMORY_SAVE:
            plan.steps.append(AgentStep(
                step_id="step_1",
                description=f"Save memory: {intent.entities.get('fact')}",
                action_type="memory_save",
                arguments={"fact": intent.entities.get("fact")}
            ))
            return plan

        if t == IntentType.MEMORY_RECALL:
            plan.steps.append(AgentStep(
                step_id="step_1",
                description="Recall memories",
                action_type="memory_recall",
                arguments={"topic": intent.entities.get("topic", "")}
            ))
            return plan

        if t == IntentType.MEMORY_FORGET:
            plan.steps.append(AgentStep(
                step_id="step_1",
                description="Forget memory",
                action_type="memory_forget",
                arguments={"pattern": intent.entities.get("pattern", "")}
            ))
            return plan

        if t == IntentType.MEMORY_CLEAR:
            plan.steps.append(AgentStep(
                step_id="step_1",
                description="Clear memories",
                action_type="memory_clear",
                arguments={},
                requires_confirmation=True,
                risk_level=AgentRiskLevel.HIGH
            ))
            return plan

        # Default: Chat / QA
        plan.steps.append(AgentStep(
            step_id="step_1",
            description="Respond to user query",
            action_type="chat",
            arguments={"query": clean}
        ))
        return plan

    def _apply_policies(self, plan: AgentPlan) -> None:
        """Classify risk level and set confirmation flags on every step."""
        for step in plan.steps:
            risk = AgentSecurityPolicy.classify_risk(step.action_type, step.arguments)
            step.risk_level = risk
            step.requires_confirmation = AgentSecurityPolicy.requires_confirmation(step.action_type, step.arguments)
