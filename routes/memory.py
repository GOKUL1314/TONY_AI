"""
Memory REST API routes for TONY (Stage 4).
Provides endpoints for creating, reading, updating, deleting, searching, and inspecting long-term memories.
"""
import logging
from flask import Blueprint, current_app, jsonify, request
from memory.extractor import is_sensitive_secret

logger = logging.getLogger("tony.routes.memory")

memory_bp = Blueprint("memory", __name__, url_prefix="/api/memory")


def _get_memory_services():
    """Access MemoryManager and MemoryRetriever from application context."""
    manager = current_app.config.get("MEMORY_MANAGER_INSTANCE")
    retriever = current_app.config.get("MEMORY_RETRIEVER_INSTANCE")
    return manager, retriever


@memory_bp.route("", methods=["GET"])
def list_memories():
    """
    List stored memories.
    Query parameters:
      - category: filter by category (e.g. 'identity', 'preference', 'project', 'skill', 'all')
      - limit: max number of records (default 100)
      - offset: pagination offset (default 0)
    """
    manager, _ = _get_memory_services()
    if not manager:
        return jsonify({"success": False, "error": "Memory subsystem is uninitialized."}), 500

    category = request.args.get("category", "all")
    try:
        limit = min(200, max(1, int(request.args.get("limit", 100))))
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        return jsonify({"success": False, "error": "Invalid limit or offset parameter."}), 400

    memories = manager.list_memories(category=category, limit=limit, offset=offset)
    return jsonify({
        "success": True,
        "count": len(memories),
        "memories": [m.to_dict() for m in memories]
    }), 200


@memory_bp.route("", methods=["POST"])
def create_memory():
    """
    Create a new memory manually.
    Expects JSON: {"memory_key": "...", "memory_value": "...", "category": "...", "importance": 1-5}
    """
    manager, _ = _get_memory_services()
    if not manager:
        return jsonify({"success": False, "error": "Memory subsystem is uninitialized."}), 500

    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type must be application/json."}), 400

    data = request.get_json(silent=True) or {}
    key = str(data.get("memory_key") or data.get("key") or "").strip()
    val = str(data.get("memory_value") or data.get("value") or "").strip()
    cat = str(data.get("category") or "other").strip()
    importance = data.get("importance", 2)

    if not key or not val:
        return jsonify({"success": False, "error": "'memory_key' (or 'key') and 'memory_value' (or 'value') are required."}), 400

    # Safety check
    if is_sensitive_secret(f"{key}: {val}"):
        return jsonify({"success": False, "error": "Safety policy: Credentials, passwords, or secrets cannot be stored."}), 400

    try:
        importance_int = max(1, min(5, int(importance)))
    except (ValueError, TypeError):
        importance_int = 2

    item = manager.save_memory(
        memory_key=key,
        memory_value=val,
        category=cat,
        importance=importance_int,
        source="api"
    )

    return jsonify({
        "success": True,
        "memory": item.to_dict()
    }), 201


@memory_bp.route("/<int:memory_id>", methods=["GET"])
def get_memory(memory_id: int):
    """Retrieve a single memory by ID."""
    manager, _ = _get_memory_services()
    if not manager:
        return jsonify({"success": False, "error": "Memory subsystem is uninitialized."}), 500

    item = manager.get_memory(memory_id)
    if not item or not item.is_active:
        return jsonify({"success": False, "error": f"Memory #{memory_id} not found."}), 404

    return jsonify({
        "success": True,
        "memory": item.to_dict()
    }), 200


@memory_bp.route("/<int:memory_id>", methods=["PUT"])
def update_memory(memory_id: int):
    """Update fields of an existing memory."""
    manager, _ = _get_memory_services()
    if not manager:
        return jsonify({"success": False, "error": "Memory subsystem is uninitialized."}), 500

    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type must be application/json."}), 400

    data = request.get_json(silent=True) or {}
    updates = dict(data)
    if "key" in updates and "memory_key" not in updates:
        updates["memory_key"] = updates["key"]
    if "value" in updates and "memory_value" not in updates:
        updates["memory_value"] = updates["value"]

    # Safety check on updated values
    val_to_check = updates.get("memory_value") or ""
    if val_to_check and is_sensitive_secret(val_to_check):
        return jsonify({"success": False, "error": "Safety policy: Credentials or secrets cannot be stored."}), 400

    updated = manager.update_memory(memory_id, updates)
    if not updated:
        return jsonify({"success": False, "error": f"Memory #{memory_id} not found."}), 404

    return jsonify({
        "success": True,
        "memory": updated.to_dict()
    }), 200


@memory_bp.route("/<int:memory_id>", methods=["DELETE"])
def delete_memory(memory_id: int):
    """Delete (deactivate) a memory by ID."""
    manager, _ = _get_memory_services()
    if not manager:
        return jsonify({"success": False, "error": "Memory subsystem is uninitialized."}), 500

    success = manager.delete_memory(memory_id)
    if not success:
        return jsonify({"success": False, "error": f"Memory #{memory_id} not found."}), 404

    return jsonify({
        "success": True,
        "message": f"Memory #{memory_id} has been deleted."
    }), 200


@memory_bp.route("", methods=["DELETE"])
def clear_all():
    """Clear all stored memories."""
    manager, _ = _get_memory_services()
    if not manager:
        return jsonify({"success": False, "error": "Memory subsystem is uninitialized."}), 500

    cleared = manager.clear_all_memories()
    return jsonify({
        "success": True,
        "cleared_count": cleared,
        "message": "All stored memories have been cleared."
    }), 200


@memory_bp.route("/search", methods=["POST"])
def search():
    """
    Search memories by query string.
    Expects JSON: {"query": "..."}
    """
    manager, _ = _get_memory_services()
    if not manager:
        return jsonify({"success": False, "error": "Memory subsystem is uninitialized."}), 500

    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type must be application/json."}), 400

    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    limit = min(50, max(1, int(data.get("limit", 10))))

    results = manager.search_memories(query, limit=limit)
    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": [m.to_dict() for m in results]
    }), 200


@memory_bp.route("/stats", methods=["GET"])
def stats():
    """Retrieve diagnostic statistics for long-term memory."""
    manager, _ = _get_memory_services()
    if not manager:
        return jsonify({"success": False, "error": "Memory subsystem is uninitialized."}), 500

    return jsonify({
        "success": True,
        "stats": manager.get_stats()
    }), 200
