"""
REST API Routes for TONY AI Personalization and Proactive Intelligence Subsystem (Stage 12).
Endpoints: /api/personalization/*
"""
import re
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app

from personalization.models import RecurrenceType, ReminderStatus
from personalization.errors import (
    PersonalizationError,
    ProfileValidationError,
    ReminderNotFoundError,
    RoutineNotFoundError
)

logger = logging.getLogger("tony.routes.personalization")

personalization_bp = Blueprint("personalization", __name__, url_prefix="/api/personalization")


def _get_manager():
    """Helper to retrieve PersonalizationManager from Flask current_app."""
    return current_app.config.get("PERSONALIZATION_MANAGER_INSTANCE")


# =============================================================================
# Profile Endpoints
# =============================================================================

@personalization_bp.route("/profile", methods=["GET"])
def get_user_profile():
    """Retrieve structured user profile."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500
    prof = mgr.profile.get_profile()
    return jsonify({"status": "success", "profile": prof.to_dict()}), 200


@personalization_bp.route("/profile", methods=["PATCH"])
def update_user_profile():
    """Update user profile attributes."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"status": "error", "error": "JSON payload required."}), 400

    try:
        updated = mgr.profile.update_profile(data)
        return jsonify({"status": "success", "profile": updated.to_dict()}), 200
    except ProfileValidationError as pve:
        return jsonify({"status": "error", "error": str(pve)}), 400
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@personalization_bp.route("/reset", methods=["POST"])
def reset_personalization_endpoint():
    """Reset user profile, clear preferences, and remove all reminders."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    res = mgr.reset_personalization()
    return jsonify(res), 200


# =============================================================================
# Preferences Endpoints
# =============================================================================

@personalization_bp.route("/preferences", methods=["GET", "POST"])
def list_preferences_endpoint():
    """List stored preferences, optionally filtered by category, or create a preference."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        key = data.get("key")
        if not key:
            return jsonify({"status": "error", "error": "Missing 'key' in request payload."}), 400
        return set_preference_endpoint(key)

    cat = request.args.get("category")
    prefs = mgr.preferences.list_preferences(category=cat)
    return jsonify({
        "status": "success",
        "count": len(prefs),
        "preferences": [p.to_dict() for p in prefs]
    }), 200


@personalization_bp.route("/preferences/<key>", methods=["GET"])
def get_preference_endpoint(key: str):
    """Get single preference by key."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    pref = mgr.preferences.get_preference(key)
    if not pref:
        return jsonify({"status": "error", "error": f"Preference '{key}' not found."}), 404
    return jsonify({"status": "success", "preference": pref.to_dict()}), 200


@personalization_bp.route("/preferences/<key>", methods=["PUT", "POST"])
def set_preference_endpoint(key: str):
    """Set or update a user preference."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    data = request.get_json(silent=True) or {}
    val = data.get("value")
    if val is None:
        return jsonify({"status": "error", "error": "Missing 'value' in request payload."}), 400

    cat = data.get("category", "general")
    source = data.get("source", "explicit_user")
    conf = float(data.get("confidence", 1.0))

    try:
        saved = mgr.preferences.set_preference(
            key=key,
            value=val,
            category=cat,
            source=source,
            confidence=conf
        )
        return jsonify({"status": "success", "preference": saved.to_dict()}), 200
    except PersonalizationError as pe:
        return jsonify({"status": "error", "error": str(pe)}), 400
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@personalization_bp.route("/preferences/<key>", methods=["DELETE"])
def delete_preference_endpoint(key: str):
    """Delete a user preference."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    ok = mgr.preferences.delete_preference(key)
    return jsonify({"status": "success", "deleted": ok}), 200


# =============================================================================
# Context Endpoint
# =============================================================================

@personalization_bp.route("/context", methods=["GET", "POST"])
def get_personalization_context():
    """Retrieve targeted personalization prompt directives for an input query."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        query = data.get("query") or data.get("message", "")
    else:
        query = request.args.get("query", "")

    ctx_str = mgr.build_context(query)
    return jsonify({"status": "success", "context": ctx_str}), 200


# =============================================================================
# Reminder Endpoints
# =============================================================================

@personalization_bp.route("/reminders", methods=["GET"])
def list_reminders_endpoint():
    """List reminders with optional filtering."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    enabled = request.args.get("enabled", "").lower() in ("true", "1")
    status = request.args.get("status")
    rems = mgr.list_reminders(enabled_only=enabled, status=status)
    return jsonify({
        "status": "success",
        "count": len(rems),
        "reminders": [r.to_dict() for r in rems]
    }), 200


@personalization_bp.route("/reminders", methods=["POST"])
def create_reminder_endpoint():
    """
    Create a scheduled reminder.
    Supports either natural language: {"text": "remind me in 10 minutes to take break"}
    Or structured: {"title": "...", "scheduled_time": "...", "recurrence": "daily"}
    """
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    data = request.get_json(silent=True) or {}
    text = data.get("text") or data.get("prompt")
    if text:
        try:
            rem = mgr.create_reminder_from_text(text)
            return jsonify({"status": "success", "reminder": rem.to_dict()}), 201
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 400

    title = data.get("title")
    sched_time = data.get("scheduled_time") or data.get("due_time")
    if not title:
        return jsonify({"status": "error", "error": "'title' is required."}), 400

    if not sched_time or not re.match(r"^\d{4}-\d{2}-\d{2}", str(sched_time)):
        parse_target = f"{title} {sched_time}" if sched_time else title
        parsed = mgr.time_parser.parse(parse_target)
        if parsed.target_time:
            sched_time = parsed.target_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            sched_time = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    desc = data.get("description", "")
    rec_str = data.get("recurrence", "none").lower()
    try:
        rec = RecurrenceType(rec_str)
    except Exception:
        rec = RecurrenceType.NONE

    tz = data.get("timezone")

    try:
        rem = mgr.create_reminder(
            title=title,
            scheduled_time=sched_time,
            description=desc,
            recurrence=rec,
            timezone=tz
        )
        return jsonify({"status": "success", "reminder": rem.to_dict()}), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 400


@personalization_bp.route("/reminders/<reminder_id>", methods=["GET"])
def get_reminder_endpoint(reminder_id: str):
    """Retrieve details of a single reminder."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    rem = mgr.get_reminder(reminder_id)
    if not rem:
        return jsonify({"status": "error", "error": f"Reminder '{reminder_id}' not found."}), 404
    return jsonify({"status": "success", "reminder": rem.to_dict()}), 200


@personalization_bp.route("/reminders/<reminder_id>", methods=["DELETE"])
def delete_reminder_endpoint(reminder_id: str):
    """Delete a reminder."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    ok = mgr.delete_reminder(reminder_id)
    return jsonify({"status": "success", "deleted": ok}), 200


@personalization_bp.route("/reminders/<reminder_id>/pause", methods=["POST"])
def pause_reminder_endpoint(reminder_id: str):
    """Pause a reminder."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    try:
        rem = mgr.pause_reminder(reminder_id)
        return jsonify({"status": "success", "reminder": rem.to_dict()}), 200
    except ReminderNotFoundError as rnfe:
        return jsonify({"status": "error", "error": str(rnfe)}), 404
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@personalization_bp.route("/reminders/<reminder_id>/resume", methods=["POST"])
def resume_reminder_endpoint(reminder_id: str):
    """Resume a paused reminder."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    try:
        rem = mgr.resume_reminder(reminder_id)
        return jsonify({"status": "success", "reminder": rem.to_dict()}), 200
    except ReminderNotFoundError as rnfe:
        return jsonify({"status": "error", "error": str(rnfe)}), 404
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@personalization_bp.route("/reminders/<reminder_id>/snooze", methods=["POST"])
def snooze_reminder_endpoint(reminder_id: str):
    """Snooze a reminder."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    data = request.get_json(silent=True) or {}
    minutes = int(data.get("minutes", 10))

    try:
        rem = mgr.snooze_reminder(reminder_id, minutes=minutes)
        return jsonify({"status": "success", "reminder": rem.to_dict()}), 200
    except ReminderNotFoundError as rnfe:
        return jsonify({"status": "error", "error": str(rnfe)}), 404
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@personalization_bp.route("/reminders/<reminder_id>/complete", methods=["POST"])
def complete_reminder_endpoint(reminder_id: str):
    """Mark a reminder as completed."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    rem = mgr.get_reminder(reminder_id)
    if not rem:
        return jsonify({"status": "error", "error": f"Reminder '{reminder_id}' not found."}), 404

    rem.status = ReminderStatus.COMPLETED
    rem.enabled = False
    rem.next_trigger_at = None
    mgr.db.save_reminder(rem)
    return jsonify({"status": "success", "reminder": rem.to_dict()}), 200


# =============================================================================
# Routines Endpoints
# =============================================================================

@personalization_bp.route("/routines", methods=["GET"])
def list_routines_endpoint():
    """List defined routines."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    rtns = mgr.list_routines()
    return jsonify({
        "status": "success",
        "count": len(rtns),
        "routines": [r.to_dict() for r in rtns]
    }), 200


@personalization_bp.route("/routines", methods=["POST"])
def create_routine_endpoint():
    """Create a new routine."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        return jsonify({"status": "error", "error": "Routine 'name' is required."}), 400

    desc = data.get("description", "")
    steps = data.get("steps", [])
    sched_time = data.get("schedule_time")
    rec_str = data.get("recurrence", "none").lower()
    try:
        rec = RecurrenceType(rec_str)
    except Exception:
        rec = RecurrenceType.NONE

    rtn = mgr.routines.create_routine(
        name=name,
        description=desc,
        steps=steps,
        schedule_time=sched_time,
        recurrence=rec
    )
    return jsonify({"status": "success", "routine": rtn.to_dict()}), 201


@personalization_bp.route("/routines/<routine_id>/run", methods=["POST"])
def run_routine_endpoint(routine_id: str):
    """Trigger execution of a routine."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    tool_exec = current_app.config.get("TOOL_EXECUTOR_INSTANCE")
    try:
        res = mgr.run_routine(routine_id, tool_executor=tool_exec)
        return jsonify({"status": "success", "execution": res}), 200
    except RoutineNotFoundError as rnfe:
        return jsonify({"status": "error", "error": str(rnfe)}), 404
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@personalization_bp.route("/routines/<routine_id>", methods=["DELETE"])
def delete_routine_endpoint(routine_id: str):
    """Delete a routine."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    ok = mgr.routines.delete_routine(routine_id)
    return jsonify({"status": "success", "deleted": ok}), 200


# =============================================================================
# Briefing & Summary Endpoints
# =============================================================================

@personalization_bp.route("/briefing", methods=["GET"])
@personalization_bp.route("/briefing/generate", methods=["POST"])
def get_morning_briefing_endpoint():
    """Generate or retrieve daily morning briefing."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    briefing = mgr.get_morning_briefing()
    return jsonify({"status": "success", "briefing": briefing.to_dict()}), 200


@personalization_bp.route("/evening_summary", methods=["GET"])
def get_evening_summary_endpoint():
    """Generate or retrieve evening summary."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    summary = mgr.get_evening_summary()
    return jsonify({"status": "success", "summary": summary.to_dict()}), 200


# =============================================================================
# Proactive Controls & Status Endpoints
# =============================================================================

@personalization_bp.route("/status", methods=["GET"])
@personalization_bp.route("/proactive", methods=["GET"])
def get_status_endpoint():
    """Retrieve proactive runtime status, quiet hours, and daily quota."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    status = mgr.get_proactive_status()
    return jsonify({"status": "success", "proactive": status}), 200


@personalization_bp.route("/proactive/toggle", methods=["POST"])
def toggle_proactive_endpoint():
    """Toggle proactive mode on or off."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    data = request.get_json(silent=True) or {}
    enable = data.get("enable", True)
    if enable:
        res = mgr.enable_proactive_mode()
    else:
        res = mgr.disable_proactive_mode()
    status = mgr.get_proactive_status()
    return jsonify({"status": "success", "proactive": status, **res}), 200


@personalization_bp.route("/proactive/enable", methods=["POST"])
def enable_proactive_endpoint():
    """Explicitly enable proactive mode."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    res = mgr.enable_proactive_mode()
    return jsonify({"status": "success", **res}), 200


@personalization_bp.route("/proactive/disable", methods=["POST"])
def disable_proactive_endpoint():
    """Explicitly disable proactive mode."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    res = mgr.disable_proactive_mode()
    return jsonify({"status": "success", **res}), 200


# =============================================================================
# Notifications Endpoints
# =============================================================================

@personalization_bp.route("/notifications", methods=["GET"])
def list_notifications_endpoint():
    """List delivered notifications."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    limit = int(request.args.get("limit", 50))
    unread = request.args.get("unread", "").lower() in ("true", "1")
    notifs = mgr.notifications.db.list_notifications(limit=limit, unread_only=unread)
    return jsonify({
        "status": "success",
        "count": len(notifs),
        "notifications": [n.to_dict() for n in notifs]
    }), 200


@personalization_bp.route("/notifications/<notif_id>/read", methods=["POST"])
def mark_notification_read_endpoint(notif_id: str):
    """Mark notification as read."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    ok = mgr.notifications.db.mark_notification_read(notif_id)
    return jsonify({"status": "success", "marked_read": ok}), 200


@personalization_bp.route("/notifications/dismiss-all", methods=["POST"])
def dismiss_all_notifications_endpoint():
    """Dismiss all unread notifications."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    mgr.notifications.db.dismiss_all_notifications()
    return jsonify({"status": "success", "message": "All notifications dismissed."}), 200


# =============================================================================
# Stats & Health Endpoints
# =============================================================================

@personalization_bp.route("/stats", methods=["GET"])
def get_stats_endpoint():
    """Subsystem metrics and counters."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "error": "Personalization subsystem not initialized."}), 500

    stats = mgr.get_stats()
    return jsonify({"status": "success", "stats": stats}), 200


@personalization_bp.route("/health", methods=["GET"])
def get_health_endpoint():
    """Health check for database, scheduler, and proactive services."""
    mgr = _get_manager()
    if not mgr:
        return jsonify({"status": "error", "healthy": False, "error": "Subsystem not initialized."}), 500

    health = mgr.check_health()
    status_str = "healthy" if health.get("healthy") else "degraded"
    return jsonify({
        "status": status_str,
        "healthy": health.get("healthy", False),
        "scheduler_running": health.get("scheduler_healthy", False),
        "health": health
    }), 200
