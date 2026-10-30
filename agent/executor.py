"""
Controlled Multi-Step Execution Engine for TONY AI Agent Subsystem (Stage 10).
Implements the plan-validate-execute-observe-recover-verify lifecycle with confirmation gates,
safe self-correction, progress telemetry, and natural response synthesis.
"""
import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

from agent.models import (
    AgentTask,
    AgentPlan,
    AgentStep,
    AgentStepStatus,
    AgentTaskStatus,
    AgentRiskLevel,
    AgentObservation,
    AgentFailure
)
from agent.policies import AgentSecurityPolicy
from agent.validator import AgentValidator
from agent.observer import AgentObserver
from agent.recovery import FailureRecoveryManager
from agent.state import AgentState
from agent.errors import AgentSecurityError, AgentExecutionError

logger = logging.getLogger("tony.agent.executor")


class AgentExecutor:
    """Orchestrates step execution across Stage 1-9 subsystems."""

    def __init__(
        self,
        tool_executor=None,
        image_manager=None,
        video_manager=None,
        vision_manager=None,
        memory_manager=None,
        memory_retriever=None,
        ai_provider=None,
        confirmation_manager=None,
        knowledge_manager=None,
        personalization_manager=None
    ):
        self.tool_executor = tool_executor
        self.image_manager = image_manager
        self.video_manager = video_manager
        self.vision_manager = vision_manager
        self.memory_manager = memory_manager
        self.memory_retriever = memory_retriever
        self.ai_provider = ai_provider
        self.confirmation_manager = confirmation_manager
        self.knowledge_manager = knowledge_manager
        self.personalization_manager = personalization_manager
        self._progress_listeners: Dict[str, List[Callable]] = {}

    def add_listener(self, task_id: str, listener: Callable) -> None:
        if task_id not in self._progress_listeners:
            self._progress_listeners[task_id] = []
        self._progress_listeners[task_id].append(listener)

    def remove_listener(self, task_id: str, listener: Callable) -> None:
        if task_id in self._progress_listeners:
            if listener in self._progress_listeners[task_id]:
                self._progress_listeners[task_id].remove(listener)

    def emit_event(self, task: AgentTask, event_type: str, step: Optional[AgentStep] = None, message: str = "") -> None:
        event = {
            "task_id": task.task_id,
            "event_type": event_type,
            "status": task.status.value,
            "step_id": step.step_id if step else None,
            "progress": task.plan.progress_percent,
            "message": message or task.natural_response or "",
            "timestamp": datetime.now().isoformat()
        }
        listeners = self._progress_listeners.get(task.task_id, [])
        for cb in listeners:
            try:
                cb(event)
            except Exception as e:
                logger.warning(f"Error in progress event callback: {e}")

    def execute_plan(self, task: AgentTask, state: AgentState) -> AgentTask:
        """
        Main execution loop for an AgentTask.
        Advances ready steps sequentially while observing, adapting, and confirming.
        """
        task.status = AgentTaskStatus.RUNNING
        task.plan.status = AgentTaskStatus.RUNNING
        self.emit_event(task, "task_started", message=f"Starting task: {task.user_goal}")

        for idx, step in enumerate(task.plan.steps):
            task.plan.current_step_index = idx
            state.current_step_index = idx
            state.current_step_id = step.step_id

            # 1. Check for Task Pause / Cancellation
            if task.is_cancelled:
                task.status = AgentTaskStatus.CANCELLED
                task.plan.status = AgentTaskStatus.CANCELLED
                step.status = AgentStepStatus.CANCELLED
                task.natural_response = "The task has been cancelled."
                self.emit_event(task, "task_cancelled", step, "Task cancelled by user.")
                return task

            if task.is_paused:
                task.status = AgentTaskStatus.PAUSED
                task.plan.status = AgentTaskStatus.PAUSED
                step.status = AgentStepStatus.PAUSED
                task.natural_response = "The task is currently paused."
                self.emit_event(task, "task_paused", step, "Task paused.")
                return task

            if step.status in (AgentStepStatus.COMPLETED, AgentStepStatus.SKIPPED, AgentStepStatus.BLOCKED):
                continue

            # 2. Check Confirmation Gate
            if step.requires_confirmation:
                conf_id = f"conf_{task.task_id}_{step.step_id}"
                task.pending_confirmation_id = conf_id
                state.pending_confirmation = {"conf_id": conf_id, "step_id": step.step_id, "description": step.description}
                task.status = AgentTaskStatus.WAITING_CONFIRMATION
                task.plan.status = AgentTaskStatus.WAITING_CONFIRMATION
                step.status = AgentStepStatus.WAITING_CONFIRMATION
                task.natural_response = (
                    f"Authorization required: {step.description}. "
                    "Do you want me to proceed? (Reply 'confirm' or 'cancel')"
                )
                self.emit_event(task, "step_waiting_confirmation", step, task.natural_response)
                return task

            # 3. Resolve Dynamic Arguments & Security Check
            try:
                resolved_args = AgentValidator.resolve_step_arguments(step, task.plan)
                permitted, reason, risk = AgentSecurityPolicy.evaluate_action(
                    step.action_type,
                    resolved_args,
                    untrusted_source=bool(step.arguments.get("untrusted_source", False))
                )
                if not permitted:
                    raise AgentSecurityError(reason or "Action rejected by security policy.")
            except Exception as val_err:
                step.status = AgentStepStatus.FAILED
                step.error = str(val_err)
                task.status = AgentTaskStatus.FAILED
                task.plan.status = AgentTaskStatus.FAILED
                task.error = str(val_err)
                task.natural_response = f"Security Policy Violation: {str(val_err)}"
                FailureRecoveryManager.block_downstream_dependencies(step.step_id, task.plan)
                self.emit_event(task, "step_failed", step, str(val_err))
                return task

            # 4. Dispatch Step with Bounded Recovery Loop
            step.status = AgentStepStatus.RUNNING
            step.started_at = datetime.now().isoformat()
            self.emit_event(task, "step_started", step, f"Executing: {step.description}")

            step_success = False
            while not step_success:
                t0 = time.time()
                try:
                    result_data = self._dispatch_action(step.action_type, resolved_args, state)
                    duration = time.time() - t0

                    # Observe and update state
                    AgentObserver.observe(step, state, result_data, duration=duration)
                    step.status = AgentStepStatus.COMPLETED
                    step.result = result_data
                    step.completed_at = datetime.now().isoformat()
                    state.completed_steps.append(step.step_id)
                    step_success = True
                    self.emit_event(task, "step_completed", step, f"Completed: {step.description}")

                except Exception as ex:
                    duration = time.time() - t0
                    err_msg = str(ex)
                    step.error = err_msg

                    # Classify failure
                    failure = FailureRecoveryManager.classify_failure(err_msg, step)
                    step.failure = failure
                    AgentObserver.observe(step, state, None, error_msg=err_msg, duration=duration)

                    # Check for self-correction (desired state already exists)
                    if FailureRecoveryManager.can_self_correct_existing_state(failure, step):
                        logger.info(f"Self-correcting step '{step.step_id}': desired state already exists.")
                        step.status = AgentStepStatus.COMPLETED
                        step.result = {"status": "already_exists", "message": err_msg}
                        step.error = None
                        step.completed_at = datetime.now().isoformat()
                        state.completed_steps.append(step.step_id)
                        step_success = True
                        self.emit_event(task, "step_completed", step, f"State already satisfied: {step.description}")
                        break

                    # Check for transient retry
                    if failure.recoverable and step.retry_count < failure.max_retries:
                        step.retry_count += 1
                        state.retry_count += 1
                        logger.warning(
                            f"Step '{step.step_id}' failed ({err_msg}). Retrying {step.retry_count}/{failure.max_retries}..."
                        )
                        self.emit_event(task, "step_retrying", step, f"Retrying step: {step.description}")
                        time.sleep(0.5)
                        continue

                    # Non-recoverable fatal failure
                    step.status = AgentStepStatus.FAILED
                    state.failed_steps.append(step.step_id)
                    task.status = AgentTaskStatus.FAILED
                    task.plan.status = AgentTaskStatus.FAILED
                    task.error = err_msg

                    # Cascading block on downstream dependent steps
                    FailureRecoveryManager.block_downstream_dependencies(step.step_id, task.plan)
                    self.emit_event(task, "step_failed", step, f"Failed: {err_msg}")
                    task.natural_response = self._synthesize_response(task)
                    return task

        # 5. Plan Completed
        task.status = AgentTaskStatus.COMPLETED
        task.plan.status = AgentTaskStatus.COMPLETED
        task.plan.completed_at = datetime.now().isoformat()
        task.result = task.plan.steps[-1].result if task.plan.steps else None
        task.natural_response = self._synthesize_response(task)
        self.emit_event(task, "task_completed", message=task.natural_response)
        return task

    def _dispatch_action(self, action_type: str, args: Dict[str, Any], state: AgentState) -> Any:
        """Dispatch concrete action to existing Stage 1-9 subsystem."""
        # 1. Image Generation
        if action_type == "image_generation":
            if not self.image_manager:
                raise AgentExecutionError("Image generation subsystem is not configured.", "step", action_type)
            prompt = args.get("prompt", "")
            res = self.image_manager.generate(prompt=prompt)
            if not res.success:
                raise AgentExecutionError(res.error_message or "Image generation failed.", "step", action_type)
            meta = res.image_metadata
            return meta.to_dict()

        # 2. Image to Video
        elif action_type == "image_to_video":
            if not self.video_manager:
                raise AgentExecutionError("Video generation subsystem is not configured.", "step", action_type)
            img_id = args.get("image_id") or state.active_image_id
            if not img_id:
                raise AgentExecutionError("No image available to animate.", "step", action_type)
            prompt = args.get("prompt")
            job = self.video_manager.start_image_to_video(image_id=img_id, prompt=prompt)
            return job.to_dict()

        # 3. Text to Video
        elif action_type == "text_to_video":
            if not self.video_manager:
                raise AgentExecutionError("Video generation subsystem is not configured.", "step", action_type)
            prompt = args.get("prompt", "")
            job = self.video_manager.start_text_to_video(prompt=prompt)
            return job.to_dict()

        # 4. Vision Actions
        elif action_type in ("vision_analyze", "vision_describe", "vision_question", "vision_ocr"):
            if not self.vision_manager:
                raise AgentExecutionError("Vision subsystem is not configured.", "step", action_type)
            from vision.models import VisionTaskType
            prompt = args.get("prompt", "")
            img_id = args.get("image_id") or state.active_image_id
            use_act = bool(args.get("use_active", False) or (img_id == state.active_image_id))

            task_type = VisionTaskType.ANALYZE
            if action_type == "vision_describe":
                task_type = VisionTaskType.DESCRIBE
            elif action_type == "vision_question":
                task_type = VisionTaskType.QUESTION
            elif action_type == "vision_ocr":
                task_type = VisionTaskType.OCR

            res = self.vision_manager.analyze(image_id=img_id, prompt=prompt, task=task_type, use_active=use_act)
            return res.to_dict()

        # 5. Safe Windows Tools
        elif action_type == "tool_execution":
            if not self.tool_executor:
                raise AgentExecutionError("Tool execution subsystem is not configured.", "step", action_type)
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
                raise AgentExecutionError(tool_res.message, "step", action_type)
            return tool_res.to_dict()

        # 6. Memory Operations
        elif action_type == "memory_save":
            if not self.memory_manager:
                raise AgentExecutionError("Memory subsystem is not configured.", "step", action_type)
            fact = args.get("fact", "")
            item = self.memory_manager.save_memory(memory_key="user_preference", memory_value=fact, category="preferences")
            return {"id": item.id, "key": item.memory_key, "value": item.memory_value}

        elif action_type == "memory_recall":
            if not self.memory_manager:
                raise AgentExecutionError("Memory subsystem is not configured.", "step", action_type)
            topic = args.get("topic", "")
            memories = self.memory_retriever.retrieve_relevant(topic, limit=5) if self.memory_retriever and topic else self.memory_manager.list_memories(is_active=True, limit=10)
            return [f"{m.memory_key}: {m.memory_value}" for m in memories]

        elif action_type == "memory_forget":
            if not self.memory_manager:
                raise AgentExecutionError("Memory subsystem is not configured.", "step", action_type)
            pattern = args.get("pattern", "")
            return {"forgotten_count": self.memory_manager.forget_by_pattern(pattern)}

        elif action_type == "memory_clear":
            if not self.memory_manager:
                raise AgentExecutionError("Memory subsystem is not configured.", "step", action_type)
            return {"cleared_count": self.memory_manager.clear_all_memories()}

        # 7. Chat / General Q&A
        elif action_type == "chat":
            if not self.ai_provider:
                return "Good day. I am TONY, your personal desktop assistant."
            query = args.get("query", "")
            return self.ai_provider.generate_response(message=query)

        # 8. Personal Knowledge & RAG Operations (Stage 11)
        elif action_type == "knowledge_search":
            if not self.knowledge_manager:
                raise AgentExecutionError("Knowledge subsystem is not configured.", "step", action_type)
            query = args.get("query", "")
            top_k = int(args.get("top_k", 5))
            results = self.knowledge_manager.search(query=query, top_k=top_k)
            return [r.to_dict() for r in results]

        elif action_type in ("knowledge_query", "knowledge_ask"):
            if not self.knowledge_manager:
                raise AgentExecutionError("Knowledge subsystem is not configured.", "step", action_type)
            question = args.get("question") or args.get("query", "")
            top_k = int(args.get("top_k", 5))
            rag_res = self.knowledge_manager.ask(question=question, top_k=top_k, ai_provider=self.ai_provider)
            return rag_res.to_dict()

        elif action_type == "knowledge_ingest":
            if not self.knowledge_manager:
                raise AgentExecutionError("Knowledge subsystem is not configured.", "step", action_type)
            path_str = args.get("path") or args.get("file_path", "")
            doc = self.knowledge_manager.ingest_file(file_path=path_str)
            return doc.to_dict()

        elif action_type == "knowledge_delete":
            if not self.knowledge_manager:
                raise AgentExecutionError("Knowledge subsystem is not configured.", "step", action_type)
            doc_id = args.get("document_id", "")
            ok = self.knowledge_manager.delete_document(doc_id)
            return {"deleted": ok, "success": ok}

        # 9. Personalization & Proactive Intelligence (Stage 12)
        elif action_type == "reminder_create":
            if not self.personalization_manager:
                raise AgentExecutionError("Personalization subsystem is not configured.", "step", action_type)
            txt = args.get("text") or args.get("prompt")
            if txt:
                rem = self.personalization_manager.create_reminder_from_text(txt)
            else:
                rem = self.personalization_manager.create_reminder(
                    title=args.get("title", "Reminder"),
                    scheduled_time=args.get("scheduled_time", ""),
                    description=args.get("description", ""),
                    recurrence=args.get("recurrence", "none")
                )
            return rem.to_dict()

        elif action_type == "reminder_list":
            if not self.personalization_manager:
                raise AgentExecutionError("Personalization subsystem is not configured.", "step", action_type)
            rems = self.personalization_manager.list_reminders()
            return [r.to_dict() for r in rems]

        elif action_type in ("reminder_delete", "reminder_cancel"):
            if not self.personalization_manager:
                raise AgentExecutionError("Personalization subsystem is not configured.", "step", action_type)
            rem_id = args.get("reminder_id") or args.get("id") or args.get("target", "")
            # Try to resolve by title or ID
            target_rem = self.personalization_manager.get_reminder(rem_id)
            if not target_rem:
                # Search by matching title
                for r in self.personalization_manager.list_reminders():
                    if rem_id.lower() in r.title.lower():
                        target_rem = r
                        break
            if target_rem:
                self.personalization_manager.cancel_reminder(target_rem.id)
                return {"success": True, "cancelled": True, "reminder_id": target_rem.id, "title": target_rem.title}
            return {"success": False, "error": f"Reminder '{rem_id}' not found."}

        elif action_type == "reminder_pause":
            if not self.personalization_manager:
                raise AgentExecutionError("Personalization subsystem is not configured.", "step", action_type)
            rem_id = args.get("reminder_id") or args.get("id", "")
            rem = self.personalization_manager.pause_reminder(rem_id)
            return rem.to_dict()

        elif action_type == "reminder_resume":
            if not self.personalization_manager:
                raise AgentExecutionError("Personalization subsystem is not configured.", "step", action_type)
            rem_id = args.get("reminder_id") or args.get("id", "")
            rem = self.personalization_manager.resume_reminder(rem_id)
            return rem.to_dict()

        elif action_type == "briefing_generate":
            if not self.personalization_manager:
                raise AgentExecutionError("Personalization subsystem is not configured.", "step", action_type)
            b = self.personalization_manager.get_morning_briefing()
            return b.to_dict()

        elif action_type == "evening_summary_generate":
            if not self.personalization_manager:
                raise AgentExecutionError("Personalization subsystem is not configured.", "step", action_type)
            s = self.personalization_manager.get_evening_summary()
            return s.to_dict()

        elif action_type == "routine_run":
            if not self.personalization_manager:
                raise AgentExecutionError("Personalization subsystem is not configured.", "step", action_type)
            rtn_id = args.get("routine_id") or args.get("id", "")
            res = self.personalization_manager.run_routine(rtn_id, tool_executor=self.tool_executor)
            return res

        elif action_type == "proactive_toggle":
            if not self.personalization_manager:
                raise AgentExecutionError("Personalization subsystem is not configured.", "step", action_type)
            enable = bool(args.get("enable", True))
            return self.personalization_manager.enable_proactive_mode() if enable else self.personalization_manager.disable_proactive_mode()

        raise AgentExecutionError(f"Unknown action type '{action_type}'.", "step", action_type)

    def _synthesize_response(self, task: AgentTask) -> str:
        """Produce authentic, natural conversational summary strictly grounded in execution."""
        plan = task.plan
        if task.status == AgentTaskStatus.CANCELLED:
            return "The task has been cancelled as requested."

        if task.status == AgentTaskStatus.FAILED:
            failed_step = next((s for s in plan.steps if s.status == AgentStepStatus.FAILED), None)
            err = failed_step.error if failed_step else (task.error or "Unknown failure")
            completed = [s for s in plan.steps if s.status == AgentStepStatus.COMPLETED]
            if completed:
                return f"I completed {len(completed)} of {len(plan.steps)} steps, but encountered an error: {err}"
            return f"I couldn't complete the task: {err}"

        if task.status == AgentTaskStatus.COMPLETED:
            # Check for multi-modal workflows
            has_img = any(s.action_type == "image_generation" for s in plan.steps)
            has_vis = any(s.action_type in ("vision_analyze", "vision_describe", "vision_question", "vision_ocr") for s in plan.steps)
            has_vid = any(s.action_type in ("image_to_video", "text_to_video") for s in plan.steps)
            has_folder = any(s.action_type == "tool_execution" and s.arguments.get("tool") == "create_folder" for s in plan.steps)

            if has_img and has_vis and has_vid and has_folder:
                return "Done. I created the image, analyzed it with vision, synthesized the video, and prepared the project folder."
            if has_img and has_vis and has_vid:
                return "Done. I created the image, analyzed it, and generated the video from it."
            if has_img and has_vis:
                vis_step = next(s for s in plan.steps if s.action_type.startswith("vision_"))
                resp_text = vis_step.result.get("response", "") if isinstance(vis_step.result, dict) else ""
                return f"Done. I created the image and analyzed it: {resp_text}"
            if has_img and has_vid:
                return "Done. I created the image and turned it into a video."

            if len(plan.steps) == 1:
                s0 = plan.steps[0]
                if s0.action_type == "reminder_create" and isinstance(s0.result, dict):
                    t = s0.result.get("title", "task")
                    st = s0.result.get("scheduled_time", "")
                    rec = s0.result.get("recurrence", "none")
                    rec_str = f" ({rec})" if rec != "none" else ""
                    return f"Done. I have scheduled a reminder to {t} at {st}{rec_str}."
                if s0.action_type == "reminder_list" and isinstance(s0.result, list):
                    if not s0.result:
                        return "You currently have no scheduled reminders."
                    return f"You have {len(s0.result)} scheduled reminder(s):\n" + "\n".join([f"• {r.get('title')} ({r.get('scheduled_time', '')[:16]})" for r in s0.result[:5]])
                if s0.action_type in ("reminder_delete", "reminder_cancel") and isinstance(s0.result, dict):
                    if s0.result.get("success"):
                        return f"Done. I've cancelled the reminder '{s0.result.get('title')}'."
                    return f"I couldn't cancel that reminder: {s0.result.get('error')}"
                if s0.action_type == "briefing_generate" and isinstance(s0.result, dict):
                    return s0.result.get("synthesized_text", "Morning briefing complete.")
                if s0.action_type == "evening_summary_generate" and isinstance(s0.result, dict):
                    return s0.result.get("synthesized_text", "Evening summary complete.")
                if s0.action_type == "routine_run" and isinstance(s0.result, dict):
                    return f"Done. Executed routine '{s0.result.get('routine_name')}' ({len(s0.result.get('steps', []))} steps)."
                if s0.action_type == "proactive_toggle" and isinstance(s0.result, dict):
                    return s0.result.get("message", "Proactive mode updated.")
                if s0.action_type in ("knowledge_query", "knowledge_ask") and isinstance(s0.result, dict):
                    return s0.result.get("answer", "Knowledge query completed.")
                if s0.action_type == "knowledge_search" and isinstance(s0.result, list):
                    return f"Found {len(s0.result)} relevant knowledge document chunks."
                if s0.action_type == "knowledge_ingest" and isinstance(s0.result, dict):
                    return f"Document '{s0.result.get('filename')}' ingested and indexed successfully."
                if s0.action_type == "chat":
                    return str(s0.result)
                if s0.action_type.startswith("vision_") and isinstance(s0.result, dict):
                    return s0.result.get("response", "Visual analysis complete.")
                if s0.action_type == "image_generation":
                    return f"Done. I created an image of {s0.arguments.get('prompt', 'your request')}."
                if s0.action_type == "tool_execution":
                    return f"Done. Executed {s0.arguments.get('tool', 'tool')} successfully."

            return "All tasks completed successfully."

        return "Task processed."
