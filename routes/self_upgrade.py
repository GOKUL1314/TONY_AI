"""
Self-Upgrade and Capabilities API routes for TONY AI.
Provides policy-guarded endpoints for system diagnostics, upgrade planning,
patch application, test execution, rollbacks, and capability registry inspection.
"""
from flask import Blueprint, current_app, jsonify, request
import logging

from self_upgrade.policy import UpgradeSecurityPolicy
from self_upgrade.errors import SelfUpgradeError, SecurityViolationError, ProtectedFileError
from intelligence.capabilities import CapabilityRegistry

logger = logging.getLogger("tony.routes.self_upgrade")

self_upgrade_bp = Blueprint("self_upgrade", __name__, url_prefix="/api")


def _get_manager():
    mgr = current_app.config.get("SELF_UPGRADE_MANAGER_INSTANCE")
    if not mgr:
        from self_upgrade.manager import SelfUpgradeManager
        project_root = current_app.config.get("BASE_DIR")
        data_dir = current_app.config.get("DATA_DIR")
        mgr = SelfUpgradeManager(project_root=project_root, data_dir=data_dir, app_context=current_app)
        current_app.config["SELF_UPGRADE_MANAGER_INSTANCE"] = mgr
    return mgr


@self_upgrade_bp.route("/intelligence/capabilities", methods=["GET"])
def get_capabilities():
    """Authoritative system capability registry across all 12 stages."""
    reg = CapabilityRegistry(app_context=current_app)
    caps = reg.get_capabilities()
    return jsonify({
        "status": "success",
        "capabilities": caps
    }), 200


@self_upgrade_bp.route("/self-upgrade/diagnose", methods=["POST", "GET"])
def diagnose():
    """Run system and intelligence diagnostic health checks."""
    mgr = _get_manager()
    report = mgr.diagnose()
    return jsonify({
        "status": "success",
        "diagnostic": report.to_dict()
    }), 200


@self_upgrade_bp.route("/self-upgrade/plan", methods=["POST"])
def create_plan():
    """
    Formulate a structured upgrade plan.
    Expects JSON: {"reason": "...", "files": ["..."], "changes": {"path": "content"}}
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "").strip()
    files = data.get("files", [])
    changes = data.get("changes", {})

    if not reason:
        return jsonify({"error": "The 'reason' field is required."}), 400
    if not files or not isinstance(files, list):
        return jsonify({"error": "The 'files' list is required."}), 400

    # Security check against prompt injection / unauthorized safety alterations
    for f in files:
        try:
            UpgradeSecurityPolicy.validate_target_path(f, current_app.config.get("BASE_DIR"))
        except (SecurityViolationError, ProtectedFileError) as sec_e:
            logger.warning(f"Self-upgrade plan rejected by security policy: {sec_e}")
            return jsonify({
                "status": "blocked",
                "error": str(sec_e),
                "message": "Security Alert: Operation rejected by safety policy."
            }), 403

    mgr = _get_manager()
    try:
        plan = mgr.create_plan(reason=reason, files_to_modify=files, proposed_changes=changes)
        return jsonify({
            "status": "success",
            "plan": plan.to_dict()
        }), 200
    except Exception as e:
        logger.error(f"Failed to create upgrade plan: {e}")
        return jsonify({"error": str(e)}), 400


@self_upgrade_bp.route("/self-upgrade/apply", methods=["POST"])
def apply_upgrade():
    """
    Apply an approved upgrade plan.
    Expects JSON: {"upgrade_id": "...", "target_test": "..."}
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True) or {}
    upgrade_id = data.get("upgrade_id", "").strip()
    target_test = data.get("target_test")

    if not upgrade_id:
        return jsonify({"error": "The 'upgrade_id' field is required."}), 400

    mgr = _get_manager()
    try:
        result = mgr.apply_upgrade(upgrade_id=upgrade_id, test_target=target_test)
        status_code = 200 if result.get("success") else 422
        return jsonify(result), status_code
    except (SecurityViolationError, ProtectedFileError) as sec_e:
        return jsonify({"error": str(sec_e), "blocked": True}), 403
    except Exception as e:
        logger.error(f"Upgrade application failed: {e}")
        return jsonify({"error": str(e)}), 500


@self_upgrade_bp.route("/self-upgrade/test", methods=["POST"])
def run_tests():
    """
    Run the test verification suite.
    Expects JSON: {"target_test": "..." (optional)}
    """
    data = request.get_json(silent=True) or {} if request.is_json else {}
    target_test = data.get("target_test")

    mgr = _get_manager()
    test_result = mgr.tester.run_tests(target_test=target_test)
    return jsonify({
        "status": "success" if test_result.success else "failed",
        "result": test_result.to_dict()
    }), 200


@self_upgrade_bp.route("/self-upgrade/rollback", methods=["POST"])
def rollback_upgrade():
    """
    Roll back an upgrade using its checkpoint backup.
    Expects JSON: {"upgrade_id": "..."}
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True) or {}
    upgrade_id = data.get("upgrade_id", "").strip()

    if not upgrade_id:
        return jsonify({"error": "The 'upgrade_id' field is required."}), 400

    mgr = _get_manager()
    try:
        res = mgr.rollback(upgrade_id)
        return jsonify(res), 200
    except Exception as e:
        logger.error(f"Rollback error for {upgrade_id}: {e}")
        return jsonify({"error": str(e)}), 500


@self_upgrade_bp.route("/self-upgrade/status", methods=["GET"])
def upgrade_status():
    """Retrieve self-upgrade engine status."""
    mgr = _get_manager()
    return jsonify(mgr.get_status()), 200


@self_upgrade_bp.route("/self-upgrade/history", methods=["GET"])
def upgrade_history():
    """Retrieve history of all upgrades."""
    mgr = _get_manager()
    history = mgr.get_history()
    return jsonify({
        "status": "success",
        "history": history
    }), 200


@self_upgrade_bp.route("/self-upgrade/<upgrade_id>", methods=["GET"])
def get_upgrade_detail(upgrade_id: str):
    """Retrieve a specific upgrade plan by ID."""
    mgr = _get_manager()
    plan_dict = mgr.history_mgr.get_upgrade(upgrade_id)
    if not plan_dict:
        return jsonify({"error": "Upgrade record not found."}), 404
    return jsonify({"upgrade": plan_dict}), 200
