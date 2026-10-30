"""
Central Intelligence and Action Orchestrator for TONY AI (Stage 8).
Coordinates intent classification, task planning, dependency resolution, execution dispatch
across Stage 1-7 subsystems, confirmation gates, error recovery, and natural response synthesis.
"""
import logging
import re
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Generator

from intelligence.models import (
    Intent,
    IntentType,
    TaskPlan,
    TaskStep,
    TaskStatus,
    StepStatus,
    ExecutionProgress
)
from intelligence.context import ConversationContext
from intelligence.intent import IntentEngine
from intelligence.planner import TaskPlanner
from intelligence.confirmations import OrchestrationConfirmationManager
from intelligence.responses import NaturalResponseEngine
from intelligence.errors import (
    IntelligenceError,
    StepExecutionError,
    SecurityRejectionError,
    sanitize_message
)
from memory.extractor import is_sensitive_secret

logger = logging.getLogger("tony.intelligence.orchestrator")


class TonyOrchestrator:
    """The central unified JARVIS intelligence engine for TONY AI."""

    def __init__(
        self,
        ai_provider=None,
        conversation_service=None,
        memory_manager=None,
        memory_retriever=None,
        memory_extractor=None,
        tool_registry=None,
        tool_executor=None,
        tool_confirmation=None,
        image_manager=None,
        video_manager=None,
        vision_manager=None,
        stt_provider=None,
        tts_provider=None,
        max_step_retries: int = 2
    ):
        self.ai_provider = ai_provider
        self.conversation_service = conversation_service
        self.memory_manager = memory_manager
        self.memory_retriever = memory_retriever
        self.memory_extractor = memory_extractor
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.tool_confirmation = tool_confirmation
        self.image_manager = image_manager
        self.video_manager = video_manager
        self.vision_manager = vision_manager
        self.stt_provider = stt_provider
        self.tts_provider = tts_provider
        self.max_step_retries = max_step_retries


        self.intent_engine = IntentEngine(tool_registry=self.tool_registry)
        self.task_planner = TaskPlanner(tool_registry=self.tool_registry)
        self.confirmation_manager = OrchestrationConfirmationManager(timeout_seconds=60)
        self.response_engine = NaturalResponseEngine()

        # Session contexts mapped by conversation_id
        self._contexts: Dict[str, ConversationContext] = {}
        # Task plans history mapped by task_id
        self._tasks: Dict[str, TaskPlan] = {}
        # Progress subscribers (task_id -> list of callback functions or queues)
        self._progress_listeners: Dict[str, List[Any]] = {}

    def get_context(self, conversation_id: str = "default_session") -> ConversationContext:
        """Retrieve or create a session conversation context."""
        if conversation_id not in self._contexts:
            self._contexts[conversation_id] = ConversationContext(conversation_id=conversation_id)
        ctx = self._contexts[conversation_id]
        ctx.sync_with_subsystems(image_manager=self.image_manager, video_manager=self.video_manager)
        return ctx

    def get_task(self, task_id: str) -> Optional[TaskPlan]:
        """Retrieve task plan by ID."""
        return self._tasks.get(task_id)

    def list_active_tasks(self) -> List[TaskPlan]:
        """List currently running or queued task plans."""
        return [
            t for t in self._tasks.values()
            if t.status in (TaskStatus.RUNNING, TaskStatus.PLANNING, TaskStatus.QUEUED, TaskStatus.WAITING_CONFIRMATION)
        ]

    def execute(self, message: str, conversation_id: str = "default_session") -> TaskPlan:
        """
        Main execution entry point:
        Processes a natural language request through Context -> Intent -> Planning -> Execution -> Response.
        """
        clean_msg = message.strip()
        ctx = self.get_context(conversation_id)

        # 1. Check for pending confirmation response in this conversation
        pending = self.confirmation_manager.get_any_active()
        if pending:
            lower = clean_msg.lower().rstrip(".!?,")
            if self.confirmation_manager.is_confirm_token(lower):
                return self.confirm_task(pending["task_id"], conversation_id=conversation_id)
            elif self.confirmation_manager.is_cancel_token(lower):
                return self.cancel_task(pending["task_id"], conversation_id=conversation_id)

        # 2. Check for security policy violations / prompt injection
        try:
            intent = self.intent_engine.detect_intent(clean_msg, context=ctx)
        except SecurityRejectionError as sec_err:
            plan = TaskPlan.create(request=clean_msg)
            plan.status = TaskStatus.FAILED
            plan.error = str(sec_err)
            plan.natural_response = "Security Alert: That action violates system safety policy and cannot be executed."
            self._record_turn(conversation_id, clean_msg, plan.natural_response)
            self._tasks[plan.task_id] = plan
            return plan

        # 3. Create TaskPlan
        try:
            plan = self.task_planner.plan(intent, clean_msg, context=ctx)
        except SecurityRejectionError as sec_err:
            plan = TaskPlan.create(request=clean_msg)
            plan.status = TaskStatus.FAILED
            plan.error = str(sec_err)
            plan.natural_response = "Security Alert: That action violates system safety policy and cannot be executed."
            self._record_turn(conversation_id, clean_msg, plan.natural_response)
            self._tasks[plan.task_id] = plan
            return plan
        except Exception as plan_err:
            logger.error(f"Planning failed for '{clean_msg}': {plan_err}")
            plan = TaskPlan.create(request=clean_msg)
            plan.status = TaskStatus.FAILED
            plan.error = str(plan_err)
            plan.natural_response = f"I could not organize a plan for that request: {plan_err}"
            self._record_turn(conversation_id, clean_msg, plan.natural_response)
            self._tasks[plan.task_id] = plan
            return plan

        self._tasks[plan.task_id] = plan
        ctx.active_task_id = plan.task_id

        # 4. Execute Plan Steps
        self._run_plan_loop(plan, ctx, start_step_index=0)

        # 5. Record Turn in History
        if plan.natural_response:
            self._record_turn(conversation_id, clean_msg, plan.natural_response)

        return plan

    def confirm_task(self, task_id: str, conversation_id: str = "default_session") -> TaskPlan:
        """Confirm a waiting high-risk step and resume execution."""
        success, plan, step_idx = self.confirmation_manager.resolve_confirmation(task_id, approved=True)
        if not success or not plan:
            # Fallback check internal tasks
            plan = self._tasks.get(task_id)
            if not plan or plan.status != TaskStatus.WAITING_CONFIRMATION:
                return TaskPlan.create("No pending confirmation found for that task.")

        ctx = self.get_context(conversation_id)
        # Mark waiting step ready to run without re-prompting
        step = plan.steps[step_idx]
        step.requires_confirmation = False
        step.status = StepStatus.PENDING

        logger.info(f"Resuming Task '{plan.task_id}' from step {step_idx} post-confirmation.")
        self._run_plan_loop(plan, ctx, start_step_index=step_idx)

        reply = f"Authorization confirmed. {plan.natural_response}"
        plan.natural_response = reply
        self._record_turn(conversation_id, "confirm", reply)
        return plan

    def cancel_task(self, task_id: Optional[str] = None, conversation_id: str = "default_session") -> TaskPlan:
        """Cancel a pending, running, or video task."""
        ctx = self.get_context(conversation_id)

        target_task_id = task_id or ctx.active_task_id
        plan = self._tasks.get(target_task_id) if target_task_id else None

        # Check pending confirmation resolution
        if target_task_id:
            self.confirmation_manager.resolve_confirmation(target_task_id, approved=False)

        # Cancel active video job if present
        if self.video_manager:
            active_vid = self.video_manager.active_video_id
            if active_vid:
                self.video_manager.cancel_job(active_vid)

        if not plan:
            plan = TaskPlan.create(request="Cancel request")
            plan.status = TaskStatus.CANCELLED
            plan.natural_response = "The active task has been cancelled."
            self._record_turn(conversation_id, "cancel", plan.natural_response)
            return plan

        plan.status = TaskStatus.CANCELLED
        plan.is_cancelled = True
        for step in plan.steps:
            if step.status in (StepStatus.PENDING, StepStatus.RUNNING, StepStatus.WAITING_CONFIRMATION):
                step.status = StepStatus.CANCELLED
                step.error = "Cancelled by user"

        plan.natural_response = self.response_engine.format_plan_response(plan)
        self._record_turn(conversation_id, "cancel", plan.natural_response)
        return plan

    def _run_plan_loop(self, plan: TaskPlan, ctx: ConversationContext, start_step_index: int = 0) -> None:
        """Sequential step execution loop with dependency resolution, retry logic, and confirmation checks."""
        plan.status = TaskStatus.RUNNING

        for idx in range(start_step_index, len(plan.steps)):
            plan.current_step_index = idx
            step = plan.steps[idx]

            # 1. Confirmation Gate Check
            if step.requires_confirmation:
                prompt = self.confirmation_manager.request_confirmation(plan, idx)
                plan.natural_response = prompt
                self._emit_progress(plan.task_id, step.step_id, idx, len(plan.steps), "WAITING_CONFIRMATION", prompt)
                return  # Halts here until user confirms or cancels

            # 2. Dependency Resolution (e.g. $step_1.result.image_id)
            self._resolve_step_arguments(step, plan, ctx)

            # 3. Execute Step with Controlled Retry Logic
            step.status = StepStatus.RUNNING
            step.started_at = datetime.now().isoformat()
            self._emit_progress(plan.task_id, step.step_id, idx, len(plan.steps), "RUNNING", f"Executing: {step.description}")

            retries = 0
            while retries <= self.max_step_retries:
                try:
                    self._dispatch_step_action(step, plan, ctx)
                    step.status = StepStatus.COMPLETED
                    step.completed_at = datetime.now().isoformat()
                    self._emit_progress(plan.task_id, step.step_id, idx, len(plan.steps), "COMPLETED", f"Completed: {step.description}")
                    break
                except Exception as step_err:
                    retries += 1
                    step.retries = retries
                    sanitized_err = sanitize_message(str(step_err))

                    # Non-retryable fatal errors (security, auth, safety, quota, validation)
                    fatal_err_keywords = ["unauthorized", "forbidden", "quota", "credit", "balance", "safety", "security", "prohibited", "401", "403", "402", "429"]
                    if any(k in sanitized_err.lower() for k in fatal_err_keywords) or retries > self.max_step_retries:
                        logger.error(f"Step '{step.step_id}' failed fatally: {sanitized_err}")
                        step.status = StepStatus.FAILED
                        step.error = sanitized_err
                        step.completed_at = datetime.now().isoformat()
                        plan.status = TaskStatus.FAILED
                        plan.error = sanitized_err
                        self._emit_progress(plan.task_id, step.step_id, idx, len(plan.steps), "FAILED", f"Failed: {sanitized_err}")
                        # Cancel any remaining dependent steps
                        for rem_step in plan.steps[idx + 1:]:
                            rem_step.status = StepStatus.CANCELLED
                            rem_step.error = f"Aborted due to preceding failure in '{step.step_id}'"
                        plan.natural_response = self.response_engine.format_plan_response(plan)
                        return

                    logger.warning(f"Step '{step.step_id}' retry {retries}/{self.max_step_retries} following error: {sanitized_err}")
                    time.sleep(0.5)

        # All steps completed successfully
        if any(s.action_type == "cancel_task" for s in plan.steps):
            plan.status = TaskStatus.CANCELLED
            progress_status = "CANCELLED"
        else:
            plan.status = TaskStatus.COMPLETED
            progress_status = "COMPLETED"

        plan.result = plan.steps[-1].result if plan.steps else None
        plan.natural_response = self.response_engine.format_plan_response(plan)
        self._emit_progress(plan.task_id, None, len(plan.steps), len(plan.steps), progress_status, plan.natural_response)

    def _resolve_step_arguments(self, step: TaskStep, plan: TaskPlan, ctx: ConversationContext) -> None:
        """Resolve dynamic argument templates like '$step_1.result.image_id' or '$step_1.result.path'."""
        resolved_args = {}
        for key, val in step.arguments.items():
            if isinstance(val, str) and val.startswith("$step_"):
                # Pattern: $step_X.result.property or $step_X.result
                parts = val[1:].split(".")
                dep_step_id = parts[0]
                dep_step = next((s for s in plan.steps if s.step_id == dep_step_id), None)
                if dep_step and dep_step.result is not None:
                    curr_val = dep_step.result
                    for sub_part in parts[1:]:
                        if sub_part == "result":
                            continue
                        if isinstance(curr_val, dict):
                            curr_val = curr_val.get(sub_part)
                        elif hasattr(curr_val, sub_part):
                            curr_val = getattr(curr_val, sub_part)
                        else:
                            curr_val = None
                            break
                    resolved_args[key] = curr_val
                else:
                    # Fallback to context
                    if "image" in key and ctx.active_image_id:
                        resolved_args[key] = ctx.active_image_id
                    elif "video" in key and ctx.active_video_id:
                        resolved_args[key] = ctx.active_video_id
                    elif "folder" in key and ctx.active_folder_path:
                        resolved_args[key] = ctx.active_folder_path
                    else:
                        resolved_args[key] = val
            else:
                resolved_args[key] = val

        step.arguments = resolved_args

    def _dispatch_step_action(self, step: TaskStep, plan: TaskPlan, ctx: ConversationContext) -> None:
        """Direct execution handler delegating to the appropriate Stage 1-7 subsystem."""
        action = step.action_type
        args = step.arguments

        # 1. Image Generation (Stage 6)
        if action == "image_generation":
            if not self.image_manager:
                raise StepExecutionError("Image generation subsystem is not configured.", step.step_id, action)
            prompt = args.get("prompt", "")
            res = self.image_manager.generate(prompt=prompt)
            if not res.success:
                raise StepExecutionError(res.error_message or "Image generation failed.", step.step_id, action)
            meta = res.image_metadata
            ctx.set_active_image(meta.image_id, path=meta.file_path, prompt=meta.prompt)
            step.result = {
                "image_id": meta.image_id,
                "file_path": meta.file_path,
                "url": meta.url,
                "prompt": meta.prompt,
                "provider": meta.provider,
                "model": meta.model
            }

        # 2. Image Editing (Stage 6)
        elif action == "image_edit":
            if not self.image_manager:
                raise StepExecutionError("Image generation subsystem is not configured.", step.step_id, action)
            instruction = args.get("instruction", "")
            res = self.image_manager.edit(instruction=instruction)
            if not res.success:
                raise StepExecutionError(res.error_message or "Image editing failed.", step.step_id, action)
            meta = res.image_metadata
            ctx.set_active_image(meta.image_id, path=meta.file_path, prompt=meta.prompt)
            step.result = meta.to_dict()

        # 3. Image Regeneration (Stage 6)
        elif action == "image_regenerate":
            if not self.image_manager:
                raise StepExecutionError("Image generation subsystem is not configured.", step.step_id, action)
            res = self.image_manager.regenerate()
            if not res.success:
                raise StepExecutionError(res.error_message or "Image regeneration failed.", step.step_id, action)
            meta = res.image_metadata
            ctx.set_active_image(meta.image_id, path=meta.file_path, prompt=meta.prompt)
            step.result = meta.to_dict()

        # 4. Image-to-Video Animation (Stage 7)
        elif action == "image_to_video":
            if not self.video_manager:
                raise StepExecutionError("Video generation subsystem is not configured.", step.step_id, action)
            img_id = args.get("image_id") or ctx.active_image_id
            if not img_id:
                raise StepExecutionError("No active image available to animate.", step.step_id, action)
            job = self.video_manager.start_image_to_video(
                image_id=img_id,
                prompt=args.get("prompt")
            )
            ctx.set_active_video(job.generation_id, prompt=args.get("prompt"))
            step.result = job.to_dict()

        # 5. Text-to-Video Generation (Stage 7)
        elif action == "text_to_video":
            if not self.video_manager:
                raise StepExecutionError("Video generation subsystem is not configured.", step.step_id, action)
            prompt = args.get("prompt", "")
            duration = args.get("duration", 5)
            fps = args.get("fps", 16)
            job = self.video_manager.start_text_to_video(
                prompt=prompt,
                duration=duration,
                fps=fps
            )
            ctx.set_active_video(job.generation_id, prompt=prompt)
            step.result = job.to_dict()

        # 5b. Vision Operations (Stage 9)
        elif action in ("vision_analyze", "vision_describe", "vision_question", "vision_ocr"):
            if not self.vision_manager:
                raise StepExecutionError("Vision subsystem is not configured.", step.step_id, action)
            prompt = args.get("prompt", "")
            img_id = args.get("image_id") or (ctx.active_image_id if args.get("use_active") else None)
            use_act = bool(args.get("use_active", False) or (img_id == ctx.active_image_id))

            from vision.models import VisionTaskType
            task_type = VisionTaskType.ANALYZE
            if action == "vision_describe":
                task_type = VisionTaskType.DESCRIBE
            elif action == "vision_question":
                task_type = VisionTaskType.QUESTION
            elif action == "vision_ocr":
                task_type = VisionTaskType.OCR

            res = self.vision_manager.analyze(
                image_id=img_id,
                prompt=prompt,
                task=task_type,
                use_active=use_act
            )
            step.result = res.to_dict()

        # 6. Safe Windows & Automation Tools (Stage 5)
        elif action == "tool_execution":

            if not self.tool_executor:
                raise StepExecutionError("Tool execution subsystem is not configured.", step.step_id, action)
            tool_name = args.get("tool")
            params = dict(args.get("parameters", {}) or {})
            if tool_name in ("open_folder", "delete_folder"):
                if "folder_path" in params and "target" not in params:
                    params["target"] = params["folder_path"]
            elif tool_name == "create_folder":
                if "folder_name" in params and "name" not in params:
                    params["name"] = params["folder_name"]

            plan_dict = {"tool": tool_name, "parameters": params}
            tool_res = self.tool_executor.execute_plan(plan_dict)
            if not tool_res.success:
                raise StepExecutionError(tool_res.message, step.step_id, action)

            # Update context if tool touched files/folders
            if tool_name == "create_folder" and "folder_path" in tool_res.data:
                ctx.set_active_folder(tool_res.data["folder_path"])
            elif tool_name == "open_folder" and "target" in params:
                ctx.set_active_folder(params["target"])
            elif tool_name == "open_folder" and "path" in params:
                ctx.set_active_folder(params["path"])
            elif tool_name in ("create_file", "open_file") and "file_path" in params:
                ctx.set_active_file(params["file_path"])

            ctx.last_tool_name = tool_name
            ctx.last_tool_result = tool_res.to_dict()
            step.result = tool_res.to_dict()

        # 7. Memory Operations (Stage 4)
        elif action == "memory_save":
            if not self.memory_manager:
                raise StepExecutionError("Memory subsystem is not configured.", step.step_id, action)
            fact = args.get("fact", "")
            if is_sensitive_secret(fact):
                raise StepExecutionError(
                    "For your security and privacy, I cannot store sensitive credentials, passwords, or API keys in memory.",
                    step.step_id, action
                )
            # Extract key/val using MemoryExtractor
            if self.memory_extractor:
                extracted = self.memory_extractor.extract(f"Remember that {fact}")
                key = extracted.memory_key or "user_preference"
                val = extracted.memory_value or fact
                cat = extracted.category or "preferences"
            else:
                key = "user_preference"
                val = fact
                cat = "preferences"

            item = self.memory_manager.save_memory(memory_key=key, memory_value=val, category=cat)
            step.result = {"id": item.id, "key": item.memory_key, "value": item.memory_value}

        elif action == "memory_recall":
            if not self.memory_manager:
                raise StepExecutionError("Memory subsystem is not configured.", step.step_id, action)
            topic = args.get("topic", "")
            memories = []
            if topic and self.memory_retriever:
                memories = self.memory_retriever.retrieve_relevant(topic, limit=5)
            if not memories:
                memories = self.memory_manager.list_memories(is_active=True, limit=10)
            items = [f"{m.memory_key.replace('_', ' ').title()}: {m.memory_value}" for m in memories]
            step.result = items

        elif action == "memory_forget":
            if not self.memory_manager:
                raise StepExecutionError("Memory subsystem is not configured.", step.step_id, action)
            pattern = args.get("pattern", "")
            count = self.memory_manager.forget_by_pattern(pattern)
            step.result = {"forgotten_count": count}

        elif action == "memory_clear":
            if not self.memory_manager:
                raise StepExecutionError("Memory subsystem is not configured.", step.step_id, action)
            cleared = self.memory_manager.clear_all_memories()
            step.result = {"cleared_count": cleared}

        # 8. Cancel Task
        elif action == "cancel_task":
            if self.video_manager and self.video_manager.active_video_id:
                self.video_manager.cancel_job(self.video_manager.active_video_id)
            step.result = {"cancelled": True}

        # 9. Conversational Chat, Research, Planning & Reasoning Steps
        elif action in ("chat", "research", "planning", "comparison", "analysis"):
            if not self.ai_provider:
                step.result = f"Completed {action} for {step.description}."
                return
            query = args.get("query") or args.get("topic") or args.get("instruction") or step.description
            # Retrieve relevant memory context if available
            memory_ctx = ""
            if self.memory_retriever:
                relevant_mems = self.memory_retriever.retrieve_relevant(str(query), limit=3)
                if relevant_mems:
                    memory_ctx = "\n".join([f"- {m.memory_key}: {m.memory_value}" for m in relevant_mems])

            # Incorporate context from preceding dependent steps if available
            prev_context = ""
            for dep_id in step.dependencies:
                dep_s = next((s for s in plan.steps if s.step_id == dep_id), None)
                if dep_s and dep_s.result:
                    prev_context += f"\n[Output from {dep_s.description}]:\n{dep_s.result}\n"

            original_req = getattr(plan, "original_request", "") or getattr(plan, "user_request", "") or ""
            if action == "chat":
                prompt = query or original_req
            else:
                prompt = f"User Request: {original_req}\nCurrent Task: {step.description}"
                if prev_context:
                    prompt += f"\nContext from previous steps:\n{prev_context}"

            system_instruction = (
                "You are TONY, a calm, intelligent, professional JARVIS-style desktop AI assistant. "
                "Address the user as Sir when appropriate. Provide concise, structured, and helpful responses. "
                "Never make false claims about actions you have not performed. Never fabricate tool results."
            )
            if memory_ctx:
                system_instruction += f"\nRelevant user preferences:\n{memory_ctx}"

            if action in ("research", "comparison"):
                from intelligence.target_scope import get_research_grounding_directive
                system_instruction += "\n\n" + get_research_grounding_directive(self.tool_registry)

            hist = [{"role": "system", "message": system_instruction}]
            try:
                ai_response = self.ai_provider.generate_response(prompt, history=hist)
                step.result = ai_response
            except TypeError:
                try:
                    ai_response = self.ai_provider.generate_response(prompt)
                    step.result = ai_response
                except Exception as e:
                    logger.warning(f"AI Provider error during {action} step: {e}")
                    step.result = f"I am at your service, Sir."
            except Exception as e:
                logger.warning(f"AI Provider error during {action} step: {e}")
                step.result = f"I am at your service, Sir."

        else:
            raise StepExecutionError(f"Unknown action type '{action}'.", step.step_id, action)

    def _emit_progress(self, task_id: str, step_id: Optional[str], step_index: int, total_steps: int, status: str, message: str) -> None:
        """Notify registered progress listeners for real-time SSE streaming or polling."""
        pct = int((step_index / max(total_steps, 1)) * 100) if total_steps > 0 else 0
        event = ExecutionProgress(
            task_id=task_id,
            step_id=step_id,
            step_index=step_index,
            total_steps=total_steps,
            status=status,
            message=message,
            percent=pct
        )
        listeners = self._progress_listeners.get(task_id, [])
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                pass

    def add_progress_listener(self, task_id: str, callback) -> None:
        """Register a callback for task execution progress events."""
        if task_id not in self._progress_listeners:
            self._progress_listeners[task_id] = []
        self._progress_listeners[task_id].append(callback)

    def remove_progress_listener(self, task_id: str, callback) -> None:
        """Unregister a task progress listener."""
        if task_id in self._progress_listeners:
            self._progress_listeners[task_id] = [c for c in self._progress_listeners[task_id] if c != callback]

    def _record_turn(self, conversation_id: str, user_text: str, assistant_text: str) -> None:
        """Store conversational turn in ConversationService and local context."""
        ctx = self.get_context(conversation_id)
        ctx.add_message("user", user_text)
        ctx.add_message("assistant", assistant_text)
        if self.conversation_service:
            try:
                self.conversation_service.add_turn(user_text, assistant_text)
            except Exception as e:
                logger.warning(f"Failed to record turn in ConversationService: {e}")
