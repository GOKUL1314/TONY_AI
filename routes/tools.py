"""
REST API Blueprint for TONY Tools Subsystem (Stage 5).
Exposes endpoints for tool discovery, direct execution, confirmation authorization,
pending action inspection, and telemetry activity logs.
"""
import logging
from flask import Blueprint, current_app, jsonify, request

logger = logging.getLogger("tony.routes.tools")

tools_bp = Blueprint("tools", __name__, url_prefix="/api/tools")


def _get_tool_services():
    """Helper to access registered tool services from Flask application context."""
    registry = current_app.config.get("TOOL_REGISTRY_INSTANCE")
    executor = current_app.config.get("TOOL_EXECUTOR_INSTANCE")
    confirmation_mgr = current_app.config.get("TOOL_CONFIRMATION_INSTANCE")
    return registry, executor, confirmation_mgr


@tools_bp.route("", methods=["GET"])
def list_tools():
    """List all registered tools with definitions, parameter schemas, and risk levels."""
    registry, _, _ = _get_tool_services()
    if not registry:
        return jsonify({"success": False, "error": "Tool subsystem uninitialized."}), 500

    category = request.args.get("category")
    if category:
        tools = registry.get_tools_by_category(category)
    else:
        tools = registry.list_tools()

    return jsonify({
        "success": True,
        "count": len(tools),
        "tools": [t.to_dict() for t in tools]
    }), 200


@tools_bp.route("/<string:tool_name>", methods=["GET"])
def get_tool(tool_name: str):
    """Retrieve details for a specific registered tool."""
    registry, _, _ = _get_tool_services()
    if not registry:
        return jsonify({"success": False, "error": "Tool subsystem uninitialized."}), 500

    tool = registry.get_tool(tool_name)
    if not tool:
        return jsonify({"success": False, "error": f"Tool '{tool_name}' not found."}), 404

    return jsonify({
        "success": True,
        "tool": tool.definition.to_dict()
    }), 200


@tools_bp.route("/execute", methods=["POST"])
def execute_tool():
    """
    Directly execute a registered tool.
    Expects JSON: {"tool": "tool_name", "parameters": {...}}
    """
    _, executor, _ = _get_tool_services()
    if not executor:
        return jsonify({"success": False, "error": "Tool executor uninitialized."}), 500

    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type must be application/json."}), 400

    data = request.get_json(silent=True) or {}
    tool_name = data.get("tool")
    if not tool_name:
        return jsonify({"success": False, "error": "The 'tool' field is required."}), 400

    parameters = data.get("parameters", {})
    if not isinstance(parameters, dict):
        return jsonify({"success": False, "error": "The 'parameters' field must be an object."}), 400

    result = executor.execute_plan({"tool": tool_name, "parameters": parameters})
    status_code = 200 if result.success or result.requires_confirmation else 400
    return jsonify(result.to_dict()), status_code


@tools_bp.route("/confirm", methods=["POST"])
def confirm_action():
    """
    Authorize and execute a pending high-risk tool action.
    Expects JSON: {"confirmation_id": "act_..."}
    """
    _, executor, _ = _get_tool_services()
    if not executor:
        return jsonify({"success": False, "error": "Tool executor uninitialized."}), 500

    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type must be application/json."}), 400

    data = request.get_json(silent=True) or {}
    confirmation_id = data.get("confirmation_id")
    if not confirmation_id:
        return jsonify({"success": False, "error": "The 'confirmation_id' field is required."}), 400

    result = executor.confirm_action(confirmation_id)
    status_code = 200 if result.success else 400
    return jsonify(result.to_dict()), status_code


@tools_bp.route("/cancel", methods=["POST"])
def cancel_action():
    """
    Cancel a pending tool action.
    Expects JSON: {"confirmation_id": "act_..."}
    """
    _, executor, _ = _get_tool_services()
    if not executor:
        return jsonify({"success": False, "error": "Tool executor uninitialized."}), 500

    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type must be application/json."}), 400

    data = request.get_json(silent=True) or {}
    confirmation_id = data.get("confirmation_id")
    if not confirmation_id:
        return jsonify({"success": False, "error": "The 'confirmation_id' field is required."}), 400

    result = executor.cancel_action(confirmation_id)
    status_code = 200 if result.success else 404
    return jsonify(result.to_dict()), status_code


@tools_bp.route("/pending", methods=["GET"])
def get_pending_actions():
    """Retrieve all active, unexpired pending confirmation actions."""
    _, _, confirmation_mgr = _get_tool_services()
    if not confirmation_mgr:
        return jsonify({"success": False, "error": "Confirmation manager uninitialized."}), 500

    pending = confirmation_mgr.list_pending()
    return jsonify({
        "success": True,
        "count": len(pending),
        "pending": [p.to_dict() for p in pending]
    }), 200


@tools_bp.route("/stats", methods=["GET"])
def get_stats():
    """Telemetry diagnostic endpoint reporting tool metrics and recent activity."""
    registry, executor, confirmation_mgr = _get_tool_services()
    if not registry or not executor or not confirmation_mgr:
        return jsonify({"success": False, "error": "Tool services uninitialized."}), 500

    return jsonify({
        "success": True,
        "stats": {
            "total_tools": registry.count(),
            "active_pending_confirmations": len(confirmation_mgr.list_pending()),
            "recent_activity": executor.get_activity_log()
        }
    }), 200
