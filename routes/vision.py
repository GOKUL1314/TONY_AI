"""
REST API Routes for TONY AI Vision Subsystem (Stage 9).
Provides endpoints for image analysis, visual question answering, OCR, history, and health.
"""
import logging
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.exceptions import BadRequest

from vision.models import VisionTaskType
from vision.errors import (
    VisionError,
    UnsupportedFormatError,
    ImageSizeExceededError,
    ImageValidationError,
    VisionProviderError,
    VisionTimeoutError,
    ImageNotFoundError
)

logger = logging.getLogger("tony.routes.vision")
vision_bp = Blueprint("vision", __name__, url_prefix="/api/vision")


def _get_vision_manager():
    """Retrieve the VisionManager instance from current_app config."""
    mgr = current_app.config.get("VISION_MANAGER_INSTANCE")
    if not mgr:
        raise RuntimeError("VisionManager is not initialized in application config.")
    return mgr


@vision_bp.route("/analyze", methods=["POST"])
def analyze_image():
    """
    Analyze an uploaded image, a stored image ID, or the active generated image.
    Accepts multipart/form-data or application/json.
    """
    try:
        manager = _get_vision_manager()

        image_bytes = None
        original_filename = None
        image_id = None
        prompt = ""
        task_str = VisionTaskType.ANALYZE.value
        use_active = False

        # 1. Parse Multipart Form
        if request.content_type and "multipart/form-data" in request.content_type:
            prompt = request.form.get("prompt", "").strip()
            task_str = request.form.get("task", VisionTaskType.ANALYZE.value).strip()
            image_id = request.form.get("image_id", "").strip() or None
            use_active = request.form.get("use_active", "false").lower() in ("true", "1", "yes")

            if "file" in request.files:
                file_obj = request.files["file"]
                if file_obj and file_obj.filename:
                    original_filename = file_obj.filename
                    image_bytes = file_obj.read()

        # 2. Parse JSON
        elif request.is_json:
            data = request.get_json(silent=True) or {}
            prompt = str(data.get("prompt", "")).strip()
            task_str = str(data.get("task", VisionTaskType.ANALYZE.value)).strip()
            image_id = data.get("image_id")
            use_active = bool(data.get("use_active", False))

        # Determine task enum
        try:
            task = VisionTaskType(task_str)
        except ValueError:
            task = VisionTaskType.ANALYZE

        result = manager.analyze(
            image_bytes=image_bytes,
            image_id=image_id,
            prompt=prompt,
            task=task,
            use_active=use_active,
            original_filename=original_filename
        )

        return jsonify({
            "success": True,
            "result": result.to_dict()
        }), 200

    except UnsupportedFormatError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "unsupported_format"}), 415
    except ImageSizeExceededError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "payload_too_large"}), 413
    except ImageValidationError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "validation_error"}), 400
    except ImageNotFoundError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "not_found"}), 404
    except VisionTimeoutError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "timeout"}), 504
    except VisionProviderError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "provider_error"}), 502
    except Exception as e:
        logger.exception("Unexpected error in /api/vision/analyze")
        return jsonify({"success": False, "error": f"Internal server error: {str(e)}"}), 500


@vision_bp.route("/question", methods=["POST"])
def visual_question():
    """Ask a question about an image."""
    try:
        manager = _get_vision_manager()

        image_bytes = None
        original_filename = None
        image_id = None
        question = ""
        use_active = False

        if request.content_type and "multipart/form-data" in request.content_type:
            question = request.form.get("question", request.form.get("prompt", "")).strip()
            image_id = request.form.get("image_id", "").strip() or None
            use_active = request.form.get("use_active", "false").lower() in ("true", "1", "yes")
            if "file" in request.files:
                file_obj = request.files["file"]
                if file_obj and file_obj.filename:
                    original_filename = file_obj.filename
                    image_bytes = file_obj.read()

        elif request.is_json:
            data = request.get_json(silent=True) or {}
            question = str(data.get("question", data.get("prompt", ""))).strip()
            image_id = data.get("image_id")
            use_active = bool(data.get("use_active", False))

        if not question:
            return jsonify({"success": False, "error": "Question is required."}), 400

        result = manager.analyze(
            image_bytes=image_bytes,
            image_id=image_id,
            prompt=question,
            task=VisionTaskType.QUESTION,
            use_active=use_active,
            original_filename=original_filename
        )

        return jsonify({
            "success": True,
            "result": result.to_dict()
        }), 200

    except UnsupportedFormatError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "unsupported_format"}), 415
    except ImageSizeExceededError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "payload_too_large"}), 413
    except ImageValidationError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "validation_error"}), 400
    except ImageNotFoundError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "not_found"}), 404
    except VisionTimeoutError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "timeout"}), 504
    except VisionProviderError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "provider_error"}), 502
    except Exception as e:
        logger.exception("Unexpected error in /api/vision/question")
        return jsonify({"success": False, "error": str(e)}), 500


@vision_bp.route("/ocr", methods=["POST"])
def extract_text():
    """Extract and read text from an image."""
    try:
        manager = _get_vision_manager()

        image_bytes = None
        original_filename = None
        image_id = None
        use_active = False

        if request.content_type and "multipart/form-data" in request.content_type:
            image_id = request.form.get("image_id", "").strip() or None
            use_active = request.form.get("use_active", "false").lower() in ("true", "1", "yes")
            if "file" in request.files:
                file_obj = request.files["file"]
                if file_obj and file_obj.filename:
                    original_filename = file_obj.filename
                    image_bytes = file_obj.read()

        elif request.is_json:
            data = request.get_json(silent=True) or {}
            image_id = data.get("image_id")
            use_active = bool(data.get("use_active", False))

        result = manager.extract_text(
            image_bytes=image_bytes,
            image_id=image_id,
            use_active=use_active
        )

        return jsonify({
            "success": True,
            "result": result.to_dict()
        }), 200

    except UnsupportedFormatError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "unsupported_format"}), 415
    except ImageSizeExceededError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "payload_too_large"}), 413
    except ImageValidationError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "validation_error"}), 400
    except ImageNotFoundError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "not_found"}), 404
    except VisionTimeoutError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "timeout"}), 504
    except VisionProviderError as e:
        return jsonify({"success": False, "error": str(e), "error_type": "provider_error"}), 502
    except Exception as e:
        logger.exception("Unexpected error in /api/vision/ocr")
        return jsonify({"success": False, "error": str(e)}), 500


@vision_bp.route("/history", methods=["GET"])
def get_history():
    """Retrieve visual analysis history."""
    try:
        manager = _get_vision_manager()
        limit = min(int(request.args.get("limit", 50)), 100)
        records = manager.list_history(limit=limit)
        return jsonify({
            "success": True,
            "records": [r.to_dict() for r in records],
            "count": len(records)
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@vision_bp.route("/<vision_id>", methods=["GET"])
def get_result_by_id(vision_id: str):
    """Retrieve a specific visual analysis record by vision_id."""
    try:
        manager = _get_vision_manager()
        record = manager.get_result(vision_id)
        if not record:
            return jsonify({"success": False, "error": f"Vision record '{vision_id}' not found."}), 404
        return jsonify({
            "success": True,
            "result": record.to_dict()
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@vision_bp.route("/image/<image_id>", methods=["GET"])
def get_uploaded_image(image_id: str):
    """Serve an uploaded image file securely."""
    try:
        manager = _get_vision_manager()
        path = manager.storage.get_image_path(image_id)
        if not path or not path.is_file():
            return jsonify({"success": False, "error": "Image file not found."}), 404

        ext = path.suffix.lower().lstrip(".")
        mimetype = f"image/{ext}" if ext in ("png", "jpeg", "webp") else ("image/jpeg" if ext == "jpg" else "application/octet-stream")
        return send_file(str(path), mimetype=mimetype)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@vision_bp.route("/health", methods=["GET"])
def health_check():
    """Health status of the vision subsystem."""
    try:
        manager = _get_vision_manager()
        health = manager.check_health()
        status_code = 200 if health.get("status") == "healthy" else 503
        return jsonify(health), status_code
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
