"""
Assistant Orchestration API Routes for TONY AI (Stage 8).
Provides endpoints for unified task execution, status polling, confirmation, cancellation,
and real-time Server-Sent Events (SSE) progress streaming.
"""
import json
import logging
import queue
import time
from datetime import datetime
from flask import Blueprint, current_app, jsonify, request, Response

from intelligence.models import TaskStatus, ExecutionProgress

logger = logging.getLogger("tony.routes.assistant")

assistant_bp = Blueprint("assistant", __name__, url_prefix="/api/assistant")


def _get_orchestrator():
    """Retrieve TonyOrchestrator instance from Flask app context."""
    return current_app.config.get("ORCHESTRATOR_INSTANCE")


@assistant_bp.route("/execute", methods=["POST"])
def execute_task():
    """
    Primary endpoint for natural language task dispatch through the Intelligence Engine.
    Expects: {"message": "...", "conversation_id": "..."}
    Returns: JSON with task_id, status, message, steps, and result.
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True) or {}
    message = data.get("message")
    if not message or not isinstance(message, str) or not message.strip():
        return jsonify({"error": "The 'message' field is required and must be non-empty."}), 400

    conversation_id = data.get("conversation_id", "default_session")
    orchestrator = _get_orchestrator()
    if not orchestrator:
        return jsonify({"error": "Tony Orchestrator is not initialized in application context."}), 500

    try:
        plan = orchestrator.execute(message=message.strip(), conversation_id=conversation_id)
        return jsonify({
            "task_id": plan.task_id,
            "status": plan.status.value if hasattr(plan.status, "value") else str(plan.status),
            "message": plan.natural_response or "Task processed.",
            "response": plan.natural_response or "Task processed.",
            "steps": [s.to_dict() for s in plan.steps],
            "result": plan.result.to_dict() if hasattr(plan.result, "to_dict") else plan.result,
            "requires_confirmation": plan.requires_confirmation,
            "pending_confirmation_id": plan.pending_confirmation_id,
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Error executing assistant task: {e}")
        return jsonify({"error": str(e)}), 500


@assistant_bp.route("/tasks/<task_id>", methods=["GET"])
def get_task(task_id: str):
    """Retrieve full status, step breakdown, and result of a specific TaskPlan."""
    orchestrator = _get_orchestrator()
    if not orchestrator:
        return jsonify({"error": "Orchestrator not initialized."}), 500

    plan = orchestrator.get_task(task_id)
    if not plan:
        return jsonify({"error": f"Task '{task_id}' not found."}), 404

    return jsonify(plan.to_dict()), 200


@assistant_bp.route("/tasks/active", methods=["GET"])
def list_active_tasks():
    """List all currently queued, planning, or running task plans."""
    orchestrator = _get_orchestrator()
    if not orchestrator:
        return jsonify({"error": "Orchestrator not initialized."}), 500

    active_tasks = orchestrator.list_active_tasks()
    return jsonify({
        "active_tasks": [t.to_dict() for t in active_tasks],
        "count": len(active_tasks)
    }), 200


@assistant_bp.route("/tasks/<task_id>/confirm", methods=["POST"])
def confirm_task(task_id: str):
    """Confirm a pending high-risk action within a TaskPlan and proceed."""
    orchestrator = _get_orchestrator()
    if not orchestrator:
        return jsonify({"error": "Orchestrator not initialized."}), 500

    plan = orchestrator.confirm_task(task_id)
    return jsonify({
        "task_id": plan.task_id,
        "status": plan.status.value if hasattr(plan.status, "value") else str(plan.status),
        "message": plan.natural_response,
        "response": plan.natural_response,
        "steps": [s.to_dict() for s in plan.steps]
    }), 200


@assistant_bp.route("/tasks/<task_id>/cancel", methods=["POST"])
def cancel_task(task_id: str):
    """Cancel a running, queued, or pending task."""
    orchestrator = _get_orchestrator()
    if not orchestrator:
        return jsonify({"error": "Orchestrator not initialized."}), 500

    plan = orchestrator.cancel_task(task_id)
    return jsonify({
        "task_id": plan.task_id,
        "status": plan.status.value if hasattr(plan.status, "value") else str(plan.status),
        "message": plan.natural_response,
        "response": plan.natural_response
    }), 200


@assistant_bp.route("/tasks/<task_id>/events", methods=["GET"])
def stream_task_events(task_id: str):
    """Server-Sent Events (SSE) live stream for task progress updates."""
    orchestrator = _get_orchestrator()
    if not orchestrator:
        return jsonify({"error": "Orchestrator not initialized."}), 500

    q: queue.Queue = queue.Queue()

    def _on_event(event: ExecutionProgress):
        q.put(event)

    orchestrator.add_progress_listener(task_id, _on_event)

    def event_stream():
        try:
            # Yield initial status
            plan = orchestrator.get_task(task_id)
            if plan:
                yield f"data: {json.dumps(plan.to_dict())}\n\n"
                if plan.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    return

            # Stream updates
            timeout_seconds = 180
            start = time.time()
            while time.time() - start < timeout_seconds:
                try:
                    event: ExecutionProgress = q.get(timeout=1.0)
                    yield f"data: {json.dumps(event.to_dict())}\n\n"
                    if event.status in ("COMPLETED", "FAILED", "CANCELLED"):
                        break
                except queue.Empty:
                    # Keep-alive heartbeat
                    yield ": keep-alive\n\n"
        finally:
            orchestrator.remove_progress_listener(task_id, _on_event)

    return Response(event_stream(), mimetype="text/event-stream")


@assistant_bp.route("/context", methods=["GET"])
def get_session_context():
    """Retrieve active session context (active media, file pointers, recent history)."""
    orchestrator = _get_orchestrator()
    if not orchestrator:
        return jsonify({"error": "Orchestrator not initialized."}), 500

    conv_id = request.args.get("conversation_id", "default_session")
    ctx = orchestrator.get_context(conv_id)
    return jsonify(ctx.to_dict()), 200
