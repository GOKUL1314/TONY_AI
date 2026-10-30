"""
Observer and Perception Engine for TONY AI Agent Subsystem (Stage 10).
Inspects step outcomes, extracts entities, records structured observations,
and synchronizes active entity context across modalities.
"""
import logging
from typing import Dict, Any, Optional
from agent.models import AgentStep, AgentObservation, AgentStepStatus
from agent.state import AgentState

logger = logging.getLogger("tony.agent.observer")


class AgentObserver:
    """Observes action results, updates agent state, and captures telemetry."""

    @classmethod
    def observe(
        cls,
        step: AgentStep,
        state: AgentState,
        result_data: Any,
        error_msg: Optional[str] = None,
        duration: float = 0.0
    ) -> AgentObservation:
        """
        Record observation and update live operational state.
        """
        detected_entities: Dict[str, Any] = {}
        status_str = "completed" if not error_msg else "failed"

        # 1. Inspect image actions
        if step.action_type in ("image_generation", "image_edit", "image_regenerate"):
            if isinstance(result_data, dict):
                img_id = result_data.get("image_id")
                img_path = result_data.get("file_path")
                if img_id:
                    state.active_image_id = img_id
                    detected_entities["image_id"] = img_id
                if img_path:
                    state.active_image_path = img_path
                    detected_entities["image_path"] = img_path

        # 2. Inspect video actions
        elif step.action_type in ("text_to_video", "image_to_video"):
            if isinstance(result_data, dict):
                vid_id = result_data.get("generation_id") or result_data.get("video_id")
                vid_path = result_data.get("file_path")
                if vid_id:
                    state.active_video_id = vid_id
                    detected_entities["video_id"] = vid_id
                if vid_path:
                    state.active_video_path = vid_path
                    detected_entities["video_path"] = vid_path

        # 3. Inspect filesystem actions
        elif step.action_type == "tool_execution":
            tool_name = step.arguments.get("tool", "")
            state.last_tool = tool_name
            state.last_result = result_data

            if isinstance(result_data, dict):
                data_dict = result_data.get("data", {})
                if tool_name == "create_folder" and "folder_path" in data_dict:
                    state.active_folder_path = data_dict["folder_path"]
                    detected_entities["folder_path"] = data_dict["folder_path"]
                elif tool_name == "open_folder":
                    folder = step.arguments.get("parameters", {}).get("folder_path") or step.arguments.get("parameters", {}).get("target")
                    if folder:
                        state.active_folder_path = folder
                        detected_entities["folder_path"] = folder
                elif tool_name in ("create_file", "open_file", "copy_file", "move_file"):
                    file_p = step.arguments.get("parameters", {}).get("file_path") or step.arguments.get("parameters", {}).get("destination")
                    if file_p:
                        state.active_file_path = file_p
                        detected_entities["file_path"] = file_p

        # 4. Inspect vision actions
        elif step.action_type in ("vision_analyze", "vision_describe", "vision_question", "vision_ocr"):
            if isinstance(result_data, dict):
                vis_id = result_data.get("vision_id")
                detected_entities["vision_id"] = vis_id
                # Untrusted content tagging
                detected_entities["untrusted_content"] = True

        # Construct structured observation
        observation = AgentObservation(
            step_id=step.step_id,
            action_type=step.action_type,
            status=status_str,
            output=result_data,
            error=error_msg,
            detected_entities=detected_entities,
            metrics={"duration_seconds": round(duration, 3)}
        )

        step.observation = observation
        return observation
