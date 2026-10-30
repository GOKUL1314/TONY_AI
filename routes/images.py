"""
REST API Blueprint for TONY AI Image Generation Subsystem (Stage 6).
Provides endpoints for generating, serving, editing, regenerating, listing, and deleting images.
"""
import logging
from flask import Blueprint, current_app, jsonify, request, send_file
from image_generation.manager import ImageGenerationManager

logger = logging.getLogger("tony.routes.images")

images_bp = Blueprint("images", __name__, url_prefix="/api/images")


def _get_image_manager() -> ImageGenerationManager:
    """Helper to access ImageGenerationManager from Flask application context."""
    manager = current_app.config.get("IMAGE_MANAGER_INSTANCE")
    if not manager:
        raise RuntimeError("ImageGenerationManager not initialized in application context.")
    return manager


@images_bp.route("/generate", methods=["POST"])
def generate_image():
    """
    Generate an image from a text prompt.
    Payload: {"prompt": "...", "width": 1024, "height": 1024, "enhance": true}
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 400

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Malformed JSON payload."}), 400

    prompt = data.get("prompt")
    if not prompt or not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "A non-empty 'prompt' field is required."}), 400

    width = int(data.get("width", current_app.config.get("IMAGE_DEFAULT_WIDTH", 1024)))
    height = int(data.get("height", current_app.config.get("IMAGE_DEFAULT_HEIGHT", 1024)))
    enhance = data.get("enhance", current_app.config.get("IMAGE_PROMPT_ENHANCEMENT", True))

    manager = _get_image_manager()
    result = manager.generate(prompt=prompt.strip(), width=width, height=height, enhance=enhance)

    if not result.success:
        return jsonify({"error": result.error_message}), result.status_code

    return jsonify({
        "status": "success",
        "image": result.image_metadata.to_dict()
    }), 201


@images_bp.route("", methods=["GET"])
def list_images():
    """
    List generated images with pagination.
    Query params: limit (default: 50), offset (default: 0)
    """
    manager = _get_image_manager()
    try:
        limit = min(100, max(1, int(request.args.get("limit", 50))))
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        return jsonify({"error": "Invalid pagination parameters."}), 400

    images = manager.list_images(limit=limit, offset=offset)
    total = manager.history.count()

    return jsonify({
        "status": "success",
        "count": len(images),
        "total": total,
        "offset": offset,
        "limit": limit,
        "images": [img.to_dict() for img in images]
    }), 200


@images_bp.route("/<image_id>", methods=["GET"])
def get_image_details(image_id: str):
    """Retrieve metadata for a specific image."""
    manager = _get_image_manager()
    image = manager.get_image(image_id)
    if not image:
        return jsonify({"error": f"Image '{image_id}' not found."}), 404

    return jsonify({
        "status": "success",
        "image": image.to_dict()
    }), 200


@images_bp.route("/<image_id>/file", methods=["GET"])
def serve_image_file(image_id: str):
    """Serve the raw PNG image file."""
    manager = _get_image_manager()
    file_path = manager.get_image_file_path(image_id)
    if not file_path or not file_path.is_file():
        return jsonify({"error": "Image file not found on disk."}), 404

    import mimetypes
    guessed, _ = mimetypes.guess_type(file_path.name)
    mimetype = guessed or ("image/jpeg" if file_path.suffix.lower() in (".jpg", ".jpeg") else "image/png")

    return send_file(
        str(file_path),
        mimetype=mimetype,
        as_attachment=False,
        download_name=file_path.name
    )


@images_bp.route("/<image_id>/regenerate", methods=["POST"])
def regenerate_image(image_id: str):
    """Regenerate an image with the original prompt."""
    manager = _get_image_manager()
    result = manager.regenerate(image_id=image_id)
    if not result.success:
        return jsonify({"error": result.error_message}), result.status_code

    return jsonify({
        "status": "success",
        "message": "Image regenerated successfully.",
        "image": result.image_metadata.to_dict()
    }), 201


@images_bp.route("/<image_id>/edit", methods=["POST"])
def edit_image(image_id: str):
    """
    Refine or edit an existing image with an instruction.
    Payload: {"instruction": "more cinematic in the rain"}
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 400

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Malformed JSON payload."}), 400

    instruction = data.get("instruction")
    if not instruction or not isinstance(instruction, str) or not instruction.strip():
        return jsonify({"error": "A non-empty 'instruction' field is required."}), 400

    width = int(data.get("width", 1024))
    height = int(data.get("height", 1024))

    manager = _get_image_manager()
    result = manager.edit(instruction=instruction.strip(), image_id=image_id, width=width, height=height)

    if not result.success:
        return jsonify({"error": result.error_message}), result.status_code

    return jsonify({
        "status": "success",
        "message": "Image refined successfully.",
        "image": result.image_metadata.to_dict()
    }), 201


@images_bp.route("/<image_id>", methods=["DELETE"])
def delete_image(image_id: str):
    """Delete an image file and its history entry."""
    manager = _get_image_manager()
    success = manager.delete_image(image_id)
    if not success:
        return jsonify({"error": f"Image '{image_id}' not found or could not be deleted."}), 404

    return jsonify({
        "status": "success",
        "message": f"Image '{image_id}' deleted successfully."
    }), 200


@images_bp.route("/status", methods=["GET"])
def image_status():
    """Retrieve image generation subsystem status and diagnostics."""
    manager = _get_image_manager()
    return jsonify(manager.get_status()), 200
