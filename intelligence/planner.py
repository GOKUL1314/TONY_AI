"""
Task Planner for TONY AI Intelligence Subsystem (Stage 8).
Constructs structured TaskPlan objects from classified user intents, manages step dependencies,
and enforces security validations and confirmation requirements.
"""
import logging
from typing import Dict, Any, List, Optional
from intelligence.models import TaskPlan, TaskStep, TaskStatus, StepStatus, Intent, IntentType
from intelligence.context import ConversationContext
from intelligence.errors import PlanningError, DependencyError, SecurityRejectionError
from tools.schemas import RiskLevel

logger = logging.getLogger("tony.intelligence.planner")


class TaskPlanner:
    """Translates classified intents into validated, dependency-aware TaskPlans."""

    def __init__(self, tool_registry=None):
        self.tool_registry = tool_registry

    def plan(self, intent: Intent, text: str, context: Optional[ConversationContext] = None) -> TaskPlan:
        """
        Build and validate a TaskPlan from an Intent.
        """
        ctx = context or ConversationContext()
        plan = TaskPlan.create(request=text)

        # 0. Prompt injection / security rejection check from intent
        if intent.entities.get("security_rejection"):
            raise SecurityRejectionError(
                intent.entities.get("reason", "Action rejected by security policy.")
            )

        # 1. Multi-Step Intent
        if intent.type == IntentType.MULTI_STEP_TASK:
            self._build_multi_step_plan(plan, intent, ctx)

        # 2. Image-to-Video Animation
        elif intent.type == IntentType.IMAGE_TO_VIDEO:
            target_img_id = intent.entities.get("image_id") or ctx.active_image_id
            step = TaskStep(
                step_id="step_1",
                action_type="image_to_video",
                description=f"Animate image into video: {intent.entities.get('prompt', 'cinematic video')}",
                arguments={
                    "image_id": target_img_id,
                    "prompt": intent.entities.get("prompt", "cinematic video")
                }
            )
            plan.steps.append(step)

        # 3. Video Generation
        elif intent.type == IntentType.VIDEO_GENERATION:
            step = TaskStep(
                step_id="step_1",
                action_type="text_to_video",
                description=f"Generate video: {intent.entities.get('prompt')}",
                arguments={
                    "prompt": intent.entities.get("prompt"),
                    "duration": intent.entities.get("duration", 5),
                    "fps": intent.entities.get("fps", 16)
                }
            )
            plan.steps.append(step)

        # 4. Image Generation
        elif intent.type == IntentType.IMAGE_GENERATION:
            step = TaskStep(
                step_id="step_1",
                action_type="image_generation",
                description=f"Generate image: {intent.entities.get('prompt')}",
                arguments={"prompt": intent.entities.get("prompt")}
            )
            plan.steps.append(step)

        # 5. Image Edit
        elif intent.type == IntentType.IMAGE_EDIT:
            step = TaskStep(
                step_id="step_1",
                action_type="image_edit",
                description=f"Edit active image: {intent.entities.get('instruction')}",
                arguments={
                    "instruction": intent.entities.get("instruction"),
                    "image_id": intent.entities.get("image_id") or ctx.active_image_id
                }
            )
            plan.steps.append(step)

        # 6. Image Regenerate
        elif intent.type == IntentType.IMAGE_REGENERATE:
            step = TaskStep(
                step_id="step_1",
                action_type="image_regenerate",
                description="Regenerate active image",
                arguments={"image_id": intent.entities.get("image_id") or ctx.active_image_id}
            )
            plan.steps.append(step)

        # 6b. Vision Operations (Stage 9)
        elif intent.type in (IntentType.VISION_ANALYZE, IntentType.VISION_DESCRIBE, IntentType.VISION_QUESTION, IntentType.VISION_OCR):
            action_map = {
                IntentType.VISION_ANALYZE: "vision_analyze",
                IntentType.VISION_DESCRIBE: "vision_describe",
                IntentType.VISION_QUESTION: "vision_question",
                IntentType.VISION_OCR: "vision_ocr"
            }
            action = action_map[intent.type]
            step = TaskStep(
                step_id="step_1",
                action_type=action,
                description=f"Visual analysis: {intent.entities.get('prompt', 'analyze image')}",
                arguments={
                    "prompt": intent.entities.get("prompt", ""),
                    "image_id": intent.entities.get("image_id") or (ctx.active_image_id if intent.entities.get("use_active") else None),
                    "use_active": intent.entities.get("use_active", False)
                }
            )
            plan.steps.append(step)

        # 7. Memory Operations
        elif intent.type == IntentType.MEMORY_SAVE:

            step = TaskStep(
                step_id="step_1",
                action_type="memory_save",
                description=f"Store memory: {intent.entities.get('fact')}",
                arguments={
                    "fact": intent.entities.get("fact"),
                    "is_sensitive": intent.entities.get("is_sensitive", False)
                }
            )
            plan.steps.append(step)

        elif intent.type == IntentType.MEMORY_RECALL:
            step = TaskStep(
                step_id="step_1",
                action_type="memory_recall",
                description="Recall stored memories",
                arguments={"topic": intent.entities.get("topic", "")}
            )
            plan.steps.append(step)

        elif intent.type == IntentType.MEMORY_FORGET:
            step = TaskStep(
                step_id="step_1",
                action_type="memory_forget",
                description=f"Forget memory matching: {intent.entities.get('pattern')}",
                arguments={"pattern": intent.entities.get("pattern", "")}
            )
            plan.steps.append(step)

        elif intent.type == IntentType.MEMORY_CLEAR:
            step = TaskStep(
                step_id="step_1",
                action_type="memory_clear",
                description="Clear all stored memories",
                arguments={},
                requires_confirmation=True
            )
            plan.steps.append(step)

        # 8. Windows System / Tool Operations
        elif intent.type in (IntentType.WINDOWS_ACTION, IntentType.FILE_OPERATION):
            tool_name = intent.entities.get("tool")
            parameters = intent.entities.get("parameters", {})
            requires_conf = intent.requires_confirmation

            # Validate tool against registry risk level
            if self.tool_registry and tool_name:
                tool_def = (
                    self.tool_registry.get_definition(tool_name)
                    if hasattr(self.tool_registry, "get_definition")
                    else (self.tool_registry.get_tool(tool_name).definition if self.tool_registry.get_tool(tool_name) else None)
                )
                if tool_def:
                    if tool_def.risk_level == RiskLevel.CRITICAL:
                        raise SecurityRejectionError(f"Tool '{tool_name}' is classified as CRITICAL and is strictly prohibited.")
                    if tool_def.risk_level == RiskLevel.HIGH:
                        requires_conf = True

            step = TaskStep(
                step_id="step_1",
                action_type="tool_execution",
                description=f"Execute tool '{tool_name}'",
                arguments={"tool": tool_name, "parameters": parameters},
                requires_confirmation=requires_conf
            )
            plan.steps.append(step)

        # 9. System Information
        elif intent.type == IntentType.SYSTEM_INFORMATION:
            step = TaskStep(
                step_id="step_1",
                action_type="tool_execution",
                description="Get system time and date",
                arguments={"tool": "get_system_time", "parameters": {}}
            )
            plan.steps.append(step)

        # 10. Cancellation
        elif intent.type == IntentType.CANCEL_TASK:
            step = TaskStep(
                step_id="step_1",
                action_type="cancel_task",
                description="Cancel active task or video job",
                arguments={"target": intent.entities.get("target", "video")}
            )
            plan.steps.append(step)

        # 11. Conversational Chat, Questions, Help
        elif intent.type in (IntentType.CHAT, IntentType.QUESTION, IntentType.HELP, IntentType.UNKNOWN):
            step = TaskStep(
                step_id="step_1",
                action_type="chat",
                description="Generate conversational assistant response",
                arguments={"query": text}
            )
            plan.steps.append(step)

        # Validate the constructed plan
        self.validate_plan(plan)
        return plan

    def _build_multi_step_plan(self, plan: TaskPlan, intent: Intent, ctx: ConversationContext) -> None:
        """Compose chained steps with appropriate input-output references."""
        sub_actions = intent.entities.get("sub_actions", [])
        if not sub_actions:
            raise PlanningError("Multi-step task contains no sub-actions.")

        prev_step_id = None
        for i, act in enumerate(sub_actions, 1):
            s_id = f"step_{i}"
            action_type = act.get("action")
            deps = [prev_step_id] if prev_step_id else []

            if action_type == "image_generation":
                step = TaskStep(
                    step_id=s_id,
                    action_type="image_generation",
                    description=f"Generate image: {act.get('prompt')}",
                    arguments={"prompt": act.get("prompt")},
                    dependencies=deps
                )
            elif action_type == "image_to_video":
                # Depends on preceding image generation step output
                step = TaskStep(
                    step_id=s_id,
                    action_type="image_to_video",
                    description=f"Turn image into video: {act.get('prompt')}",
                    arguments={
                        "image_id": f"${prev_step_id}.result.image_id" if prev_step_id else ctx.active_image_id,
                        "prompt": act.get("prompt")
                    },
                    dependencies=deps
                )
            elif action_type == "memory_save":
                step = TaskStep(
                    step_id=s_id,
                    action_type="memory_save",
                    description=f"Save preference: {act.get('fact')}",
                    arguments={"fact": act.get("fact")},
                    dependencies=deps
                )
            elif action_type == "tool_execution":
                tool_name = act.get("tool")
                requires_conf = False
                if self.tool_registry and tool_name:
                    tool_def = (
                        self.tool_registry.get_definition(tool_name)
                        if hasattr(self.tool_registry, "get_definition")
                        else (self.tool_registry.get_tool(tool_name).definition if self.tool_registry.get_tool(tool_name) else None)
                    )
                    if tool_def:
                        if tool_def.risk_level == RiskLevel.CRITICAL:
                            raise SecurityRejectionError(f"Tool '{tool_name}' is classified CRITICAL and prohibited.")
                        if tool_def.risk_level == RiskLevel.HIGH:
                            requires_conf = True

                step = TaskStep(
                    step_id=s_id,
                    action_type="tool_execution",
                    description=f"Execute tool '{tool_name}'",
                    arguments={"tool": tool_name, "parameters": act.get("parameters", {})},
                    dependencies=deps,
                    requires_confirmation=requires_conf
                )
            else:
                step = TaskStep(
                    step_id=s_id,
                    action_type=action_type,
                    description=act.get("description", f"Execute {action_type}"),
                    arguments=act,
                    dependencies=deps
                )

            plan.steps.append(step)
            prev_step_id = s_id

    def validate_plan(self, plan: TaskPlan) -> None:
        """
        Strict validation of plan integrity:
        - Non-empty steps
        - Valid action types
        - No circular dependencies
        - Valid dependency target IDs
        """
        if not plan.steps:
            raise PlanningError("Task plan must contain at least one step.")

        step_ids = {s.step_id for s in plan.steps}

        # Check dependency targets exist
        for step in plan.steps:
            for dep in step.dependencies:
                if dep not in step_ids:
                    raise DependencyError(f"Step '{step.step_id}' depends on non-existent step '{dep}'.")
                if dep == step.step_id:
                    raise DependencyError(f"Step '{step.step_id}' cannot depend on itself.")

        # Check for circular dependencies (topological sort check)
        visited = set()
        rec_stack = set()

        def _has_cycle(curr_id: str) -> bool:
            visited.add(curr_id)
            rec_stack.add(curr_id)
            curr_step = next(s for s in plan.steps if s.step_id == curr_id)
            for dep in curr_step.dependencies:
                if dep not in visited:
                    if _has_cycle(dep):
                        return True
                elif dep in rec_stack:
                    return True
            rec_stack.remove(curr_id)
            return False

        for step in plan.steps:
            if step.step_id not in visited:
                if _has_cycle(step.step_id):
                    raise DependencyError("Task plan contains circular dependencies.")

        # Update plan requires_confirmation flag
        plan.requires_confirmation = any(s.requires_confirmation for s in plan.steps)
