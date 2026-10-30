"""
Agentic Execution and Task Management REST API Routes for TONY AI (Stage 10).
Provides endpoints for multi-step task execution, DAG inspection, human-in-the-loop confirmation,
pause/resume/cancel controls, and real-time SSE progress streaming.
"""
import json
import logging
import queue
import time
from datetime import datetime
from flask import Blueprint, current_app, jsonify, request, Response

from agent.models import AgentTaskStatus, AgentStepStatus
from agent.errors import AgentExecutionError, AgentSecurityError

logger = logging.getLogger("tony.routes.agent")

agent_bp = Blueprint("agent", __name__, url_prefix="/api/agent")


def _get_agent_manager():
    """Retrieve AgentManager instance from Flask app configuration."""
    return current_app.config.get("AGENT_MANAGER_INSTANCE")


@agent_bp.route("/execute", methods=["POST"])
def execute_agent_task():
    """
    Execute a natural language goal through the Stage 10 Agent Engine.
    Body: {"message": "...", "goal": "...", "conversation_id": "..."}
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True) or {}
    goal = data.get("goal") or data.get("message")
    if not goal or not isinstance(goal, str) or not goal.strip():
        return jsonify({"error": "A non-empty 'goal' or 'message' field is required."}), 400

    conversation_id = data.get("conversation_id", "default_session")
    manager = _get_agent_manager()
    if not manager:
        return jsonify({"error": "Agent Manager is not initialized in application context."}), 500

    try:
        task = manager.execute(user_goal=goal.strip(), conversation_id=conversation_id)
        return jsonify(task.to_dict()), 200
    except AgentSecurityError as sec_err:
        logger.warning(f"Security policy violation in agent execute: {sec_err}")
        return jsonify({"error": str(sec_err), "status": "failed", "security_violation": True}), 403
    except Exception as e:
        logger.error(f"Error executing agent task: {e}")
        return jsonify({"error": str(e), "status": "failed"}), 500


@agent_bp.route("/tasks", methods=["GET"])
def list_tasks():
    """List agent tasks, optionally filtered by status."""
    manager = _get_agent_manager()
    if not manager:
        return jsonify({"error": "Agent Manager not initialized."}), 500

    status = request.args.get("status")
    limit = int(request.args.get("limit", 50))
    tasks = manager.list_tasks(status=status, limit=limit)
    return jsonify({
        "tasks": [t.to_dict() for t in tasks],
        "count": len(tasks)
    }), 200


@agent_bp.route("/tasks/active", methods=["GET"])
def list_active_tasks():
    """List currently active agent tasks."""
    manager = _get_agent_manager()
    if not manager:
        return jsonify({"error": "Agent Manager not initialized."}), 500

    active_tasks = manager.list_active_tasks()
    return jsonify({
        "active_tasks": [t.to_dict() for t in active_tasks],
        "count": len(active_tasks)
    }), 200


@agent_bp.route("/tasks/<task_id>", methods=["GET"])
def get_task(task_id: str):
    """Retrieve full task details, execution plan, steps, and observations."""
    manager = _get_agent_manager()
    if not manager:
        return jsonify({"error": "Agent Manager not initialized."}), 500

    task = manager.get_task(task_id)
    if not task:
        return jsonify({"error": f"Agent task '{task_id}' not found."}), 404

    return jsonify(task.to_dict()), 200


@agent_bp.route("/tasks/<task_id>/confirm", methods=["POST"])
def confirm_task_step(task_id: str):
    """Approve a pending confirmation step in an agent task."""
    manager = _get_agent_manager()
    if not manager:
        return jsonify({"error": "Agent Manager not initialized."}), 500

    data = request.get_json(silent=True) or {}
    conf_id = data.get("confirmation_id")

    try:
        task = manager.confirm_task(task_id, confirmation_id=conf_id)
        return jsonify(task.to_dict()), 200
    except AgentExecutionError as ae:
        return jsonify({"error": str(ae)}), 400
    except Exception as e:
        logger.error(f"Error confirming task '{task_id}': {e}")
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/tasks/<task_id>/cancel", methods=["POST"])
def cancel_agent_task(task_id: str):
    """Cancel an executing, paused, or pending agent task."""
    manager = _get_agent_manager()
    if not manager:
        return jsonify({"error": "Agent Manager not initialized."}), 500

    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "Cancelled by user via API.")

    try:
        task = manager.cancel_task(task_id, reason=reason)
        return jsonify(task.to_dict()), 200
    except AgentExecutionError as ae:
        return jsonify({"error": str(ae)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/tasks/<task_id>/pause", methods=["POST"])
def pause_agent_task(task_id: str):
    """Pause an executing agent task."""
    manager = _get_agent_manager()
    if not manager:
        return jsonify({"error": "Agent Manager not initialized."}), 500

    try:
        task = manager.pause_task(task_id)
        return jsonify(task.to_dict()), 200
    except AgentExecutionError as ae:
        return jsonify({"error": str(ae)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/tasks/<task_id>/resume", methods=["POST"])
def resume_agent_task(task_id: str):
    """Resume a paused agent task."""
    manager = _get_agent_manager()
    if not manager:
        return jsonify({"error": "Agent Manager not initialized."}), 500

    try:
        task = manager.resume_task(task_id)
        return jsonify(task.to_dict()), 200
    except AgentExecutionError as ae:
        return jsonify({"error": str(ae)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/tasks/<task_id>/retry", methods=["POST"])
def retry_agent_task(task_id: str):
    """Retry a failed agent task from the point of failure."""
    manager = _get_agent_manager()
    if not manager:
        return jsonify({"error": "Agent Manager not initialized."}), 500

    try:
        task = manager.retry_task(task_id)
        return jsonify(task.to_dict()), 200
    except AgentExecutionError as ae:
        return jsonify({"error": str(ae)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/tasks/<task_id>/events", methods=["GET"])
def stream_task_events(task_id: str):
    """Server-Sent Events (SSE) live progress stream for an agent task."""
    manager = _get_agent_manager()
    if not manager:
        return jsonify({"error": "Agent Manager not initialized."}), 500

    q: queue.Queue = queue.Queue()

    def _listener(evt: dict):
        q.put(evt)

    manager.add_listener(task_id, _listener)

    def event_stream():
        try:
            # Yield current state first
            task = manager.get_task(task_id)
            if task:
                yield f"data: {json.dumps(task.to_dict())}\n\n"
                if task.status in (AgentTaskStatus.COMPLETED, AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED):
                    return

            timeout_seconds = 180
            start = time.time()
            while time.time() - start < timeout_seconds:
                try:
                    event = q.get(timeout=1.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("event_type") in ("task_completed", "task_failed", "task_cancelled"):
                        break
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            manager.remove_listener(task_id, _listener)

    return Response(event_stream(), mimetype="text/event-stream")


@agent_bp.route("/state", methods=["GET"])
def get_session_state():
    """Retrieve operational state for a conversation session."""
    manager = _get_agent_manager()
    if not manager:
        return jsonify({"error": "Agent Manager not initialized."}), 500

    conv_id = request.args.get("conversation_id", "default_session")
    state = manager.get_state(conv_id)
    return jsonify(state.to_dict()), 200
