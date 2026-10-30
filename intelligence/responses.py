"""
Natural Response Engine for TONY AI (Stage 8).
Generates calm, concise, intelligent, and context-aware JARVIS-style dialogue responses
strictly grounded in real execution results, with zero false action claims.
"""
import logging
from typing import Optional, Dict, Any, List
from intelligence.models import TaskPlan, TaskStep, TaskStatus, StepStatus

logger = logging.getLogger("tony.intelligence.responses")


class NaturalResponseEngine:
    """Produces authentic, natural conversational responses based strictly on actual task execution."""

    @classmethod
    def format_plan_response(cls, plan: TaskPlan) -> str:
        """
        Synthesize a natural language summary from a finished or in-progress TaskPlan.
        """
        # 1. Plan Waiting for User Confirmation
        if plan.status == TaskStatus.WAITING_CONFIRMATION:
            curr_step = plan.steps[plan.current_step_index] if plan.current_step_index < len(plan.steps) else None
            desc = curr_step.description if curr_step else "This action"
            return (
                f"Authorization required before proceeding: {desc}. "
                f"Would you like me to continue? (Reply 'yes' or 'confirm' to proceed, or 'no' to cancel)"
            )

        # 2. Plan Cancelled
        if plan.status == TaskStatus.CANCELLED:
            orig_req = getattr(plan, "original_request", "") or getattr(plan, "user_request", "") or ""
            if any(s.action_type in ("image_to_video", "text_to_video", "cancel_task") for s in plan.steps) or "video" in orig_req.lower():
                return "The video generation task has been cancelled."
            return "The task has been cancelled as requested."

        # 3. Plan Failed
        if plan.status == TaskStatus.FAILED:
            # Check for partial multi-step success (e.g. image succeeded, video failed)
            completed_steps = [s for s in plan.steps if s.status == StepStatus.COMPLETED]
            failed_step = next((s for s in plan.steps if s.status == StepStatus.FAILED), None)
            err_msg = failed_step.error if failed_step else (plan.error or "Unknown error")

            has_img_success = any(s.action_type == "image_generation" for s in completed_steps)
            has_vid_fail = failed_step and failed_step.action_type in ("image_to_video", "text_to_video")

            if has_img_success and has_vid_fail:
                return f"The image was created successfully, but the video generation could not be completed ({err_msg}). You can still access the generated image."

            return f"I couldn't complete the task: {err_msg}"

        # 4. Multi-Step Success
        if len(plan.steps) > 1 and plan.status == TaskStatus.COMPLETED:
            return cls._format_multi_step_success(plan.steps)

        # 5. Single-Step Success
        if len(plan.steps) == 1 and plan.status == TaskStatus.COMPLETED:
            return cls._format_single_step_success(plan.steps[0])

        return "Task completed."

    @classmethod
    def _format_single_step_success(cls, step: TaskStep) -> str:
        action = step.action_type
        res = step.result

        if action == "image_generation":
            prompt = step.arguments.get("prompt", "image")
            is_mock = isinstance(res, dict) and res.get("provider") == "mock"
            if is_mock:
                return f"Done. I created an image of {prompt} (offline mock simulation). It's ready on your screen. Configure IMAGE_API_KEY in .env for real AI generation."
            return f"Done. I created an image of {prompt}. It's ready on your screen."

        if action == "image_edit":
            instruction = step.arguments.get("instruction", "requested style")
            is_mock = isinstance(res, dict) and res.get("provider") == "mock"
            if is_mock:
                return f"Done. I've updated the image to be {instruction} (offline mock simulation)."
            return f"Done. I've updated the image to be {instruction}."

        if action == "image_regenerate":
            is_mock = isinstance(res, dict) and res.get("provider") == "mock"
            if is_mock:
                return "Done. I have regenerated the image for you (offline mock simulation)."
            return "Done. I have regenerated the image for you."

        if action == "text_to_video":
            prompt = step.arguments.get("prompt", "video")
            # If job is still running / async
            if isinstance(res, dict) and res.get("status") in ("queued", "processing"):
                return f"Understood. I'm generating your video of {prompt} now. You can track its progress in the Video Studio."
            return f"Done. I created the video of {prompt}."

        if action == "image_to_video":
            if isinstance(res, dict) and res.get("status") in ("queued", "processing"):
                return "Understood. I'm animating the image into a video now. You can track progress in the Video Studio."
            return "Done. I've animated the image into a cinematic video."

        if action == "tool_execution":
            tool_name = step.arguments.get("tool")
            msg = res.get("message") if isinstance(res, dict) else (getattr(res, "message", None) or "")
            if msg:
                return f"Done. {msg}"
            return f"Done. Executed {tool_name} successfully."

        if action == "memory_save":
            fact = step.arguments.get("fact", "that")
            return f"Understood. I will remember that."

        if action == "memory_recall":
            if isinstance(res, list) and res:
                formatted = "\n".join([f"- {item}" for item in res])
                return f"Here is what I have saved in memory:\n{formatted}"
            elif isinstance(res, str) and res:
                return res
            return "I don't have any specific memories saved regarding that."

        if action == "memory_forget":
            pat = step.arguments.get("pattern", "that")
            return f"Done. I have removed stored memories regarding '{pat}'."

        if action == "memory_clear":
            return "All stored memories have been cleared from long-term storage."

        if action in ("vision_analyze", "vision_describe", "vision_question", "vision_ocr"):
            if isinstance(res, dict) and "response" in res:
                return res["response"]
            return str(res) if res else "I have completed the visual analysis."

        if action == "cancel_task":
            return "The active task has been cancelled."

        if action in ("chat", "research", "planning", "comparison", "analysis"):
            return str(res) if res else "How may I assist you further?"

        return "Done."


    @classmethod
    def _format_multi_step_success(cls, steps: List[TaskStep]) -> str:
        """Compose a concise unified JARVIS summary of completed multi-step pipeline."""
        has_image = any(s.action_type == "image_generation" for s in steps)
        has_video = any(s.action_type in ("image_to_video", "text_to_video") for s in steps)
        has_memory = any(s.action_type == "memory_save" for s in steps)
        tool_steps = [s for s in steps if s.action_type == "tool_execution"]

        if has_image and has_video:
            img_step = next(s for s in steps if s.action_type == "image_generation")
            prompt = img_step.arguments.get("prompt", "your request")
            mem_addon = " and saved your preference to memory" if has_memory else ""
            return f"Done. I created the {prompt} image, turned it into a cinematic video{mem_addon}."

        if tool_steps and len(tool_steps) == len(steps):
            tools_used = [s.arguments.get("tool", "") for s in tool_steps]
            if "volume_up" in tools_used and "open_website" in tools_used:
                web_step = next(s for s in tool_steps if s.arguments.get("tool") == "open_website")
                site = web_step.arguments.get("parameters", {}).get("target", "the requested site")
                return f"Done. Increased the volume and opened {site}."
            if "create_folder" in tools_used and "open_folder" in tools_used:
                fold_step = next(s for s in tool_steps if s.arguments.get("tool") == "create_folder")
                name = fold_step.arguments.get("parameters", {}).get("folder_name", "folder")
                return f"Done. Created the folder '{name}' and opened it."
            if "open_folder" in tools_used and "search_files" in tools_used:
                return "Done. Opened the project folder and searched for matching media files."

        # Check for reasoning / research / planning multi-step pipelines
        reasoning_steps = [s for s in steps if s.action_type in ("research", "planning", "comparison", "analysis")]
        if reasoning_steps:
            valid_results = [s.result for s in reasoning_steps if s.result and isinstance(s.result, str)]
            if len(valid_results) > 1:
                return "\n\n".join(valid_results)
            elif valid_results:
                return valid_results[-1]

        # Generic multi-step completion
        descriptions = [s.description for s in steps if s.status == StepStatus.COMPLETED]
        return "All tasks completed successfully: " + "; ".join(descriptions)
