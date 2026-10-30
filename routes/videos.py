"""
REST API Blueprint for TONY AI Video Generation Subsystem (Stage 7).
Provides asynchronous job endpoints for creating, status polling, serving,
cancelling, regenerating, listing, and deleting video assets.
"""
import logging
from flask import Blueprint, current_app, jsonify, request, send_file
from video_generation.manager import VideoGenerationManager
from video_generation.errors import (
    VideoGenerationError,
    VideoAuthenticationError,
    VideoValidationError,
    SafetyViolationError,
    FreeQuotaUnavailableError,
    LocalVideoUnavailableError,
    PaidProviderBlockedError,
    UnsupportedVideoCapabilityError,
    ProviderUnavailableError,
    VideoNotFoundError
)

logger = logging.getLogger("tony.routes.videos")

videos_bp = Blueprint("videos", __name__, url_prefix="/api/videos")


def _get_video_manager() -> VideoGenerationManager:
    """Helper to access VideoGenerationManager from Flask application context."""
    manager = current_app.config.get("VIDEO_MANAGER_INSTANCE")
    if not manager:
        raise RuntimeError("VideoGenerationManager not initialized in application context.")
    return manager


@videos_bp.route("/generate", methods=["POST"])
def generate_video():
    """
    Queue an asynchronous video generation job (Text-to-Video or Image-to-Video).
    Payload:
      {
        "prompt": "a futuristic flying vehicle",
        "duration": 5,
        "width": 512,
        "height": 512,
        "fps": 16,
        "enhance": true,
        "seed": 42,
        "negative_prompt": "blurry",
        "image_id": "img_..." (optional for image-to-video)
      }
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 400

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Malformed JSON payload."}), 400

    manager = _get_video_manager()
    image_id = data.get("image_id")
    prompt = data.get("prompt", "")
    duration = data.get("duration")
    width = data.get("width")
    height = data.get("height")
    fps = data.get("fps")
    enhance = data.get("enhance")
    seed = data.get("seed")
    negative_prompt = data.get("negative_prompt")

    try:
        if image_id:
            # Image-to-Video workflow
            job = manager.start_image_to_video(
                image_id=str(image_id).strip(),
                prompt=prompt if prompt else None,
                duration=int(duration) if duration is not None else None,
                width=int(width) if width is not None else None,
                height=int(height) if height is not None else None,
                fps=int(fps) if fps is not None else None,
                seed=int(seed) if seed is not None else None
            )
        else:
            # Text-to-Video workflow
            if not prompt or not isinstance(prompt, str) or not prompt.strip():
                return jsonify({"error": "A non-empty 'prompt' field is required."}), 400

            job = manager.start_text_to_video(
                prompt=prompt.strip(),
                duration=int(duration) if duration is not None else None,
                width=int(width) if width is not None else None,
                height=int(height) if height is not None else None,
                fps=int(fps) if fps is not None else None,
                enhance=bool(enhance) if enhance is not None else None,
                seed=int(seed) if seed is not None else None,
                negative_prompt=negative_prompt.strip() if negative_prompt else None
            )

        return jsonify({
            "status": "queued",
            "generation_id": job.generation_id,
            "job": job.to_dict()
        }), 202

    except VideoValidationError as e:
        return jsonify({"error": e.message, "code": e.code}), 400
    except SafetyViolationError as e:
        return jsonify({"error": e.message, "code": e.code}), 400
    except UnsupportedVideoCapabilityError as e:
        return jsonify({"error": e.message, "code": e.code}), 400
    except VideoAuthenticationError as e:
        return jsonify({"error": e.message, "code": e.code}), 401
    except FreeQuotaUnavailableError as e:
        return jsonify({"error": e.message, "code": e.code}), 402
    except PaidProviderBlockedError as e:
        return jsonify({"error": e.message, "code": e.code}), 403
    except (LocalVideoUnavailableError, ProviderUnavailableError) as e:
        return jsonify({"error": e.message, "code": e.code}), 503
    except Exception as e:
        logger.exception(f"Unexpected error starting video job: {e}")
        return jsonify({"error": f"Failed to initiate video generation: {e}"}), 500


@videos_bp.route("/<generation_id>/status", methods=["GET"])
@videos_bp.route("/jobs/<generation_id>", methods=["GET"])
def get_video_status(generation_id: str):
    """
    Lightweight polling endpoint for in-flight or completed video jobs.
    """
    manager = _get_video_manager()
    job = manager.get_job_status(generation_id)

    if job:
        return jsonify({
            "status": "success",
            "generation_id": job.generation_id,
            "job_status": job.status,
            "progress": job.progress,
            "progress_message": job.progress_message,
            "video": job.video_metadata.to_dict() if job.video_metadata else None,
            "error": job.error,
            "is_cancelled": job.is_cancelled
        }), 200

    # If job not in memory, check persistent history
    video = manager.get_video(generation_id)
    if video:
        return jsonify({
            "status": "success",
            "generation_id": video.video_id,
            "job_status": "completed",
            "progress": 100,
            "progress_message": "Video generation complete",
            "video": video.to_dict(),
            "error": None,
            "is_cancelled": False
        }), 200

    return jsonify({"error": f"Video job '{generation_id}' not found."}), 404


@videos_bp.route("", methods=["GET"])
@videos_bp.route("/history", methods=["GET"])
def list_videos():
    """
    List historical generated videos with pagination.
    Query params: limit (default 50), offset (default 0)
    """
    manager = _get_video_manager()
    try:
        limit = min(100, max(1, int(request.args.get("limit", 50))))
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        return jsonify({"error": "Invalid pagination parameters."}), 400

    videos = manager.list_videos(limit=limit, offset=offset)
    total = manager.history.count()

    return jsonify({
        "status": "success",
        "count": len(videos),
        "total": total,
        "offset": offset,
        "limit": limit,
        "videos": [v.to_dict() for v in videos]
    }), 200


@videos_bp.route("/<video_id>", methods=["GET"])
def get_video_details(video_id: str):
    """Retrieve full details of a specific video asset."""
    manager = _get_video_manager()
    video = manager.get_video(video_id)
    if not video:
        return jsonify({"error": f"Video '{video_id}' not found."}), 404

    return jsonify({
        "status": "success",
        "video": video.to_dict()
    }), 200


@videos_bp.route("/<video_id>/file", methods=["GET"])
def serve_video_file(video_id: str):
    """Serve the raw MP4 video file stream."""
    manager = _get_video_manager()
    file_path = manager.get_video_file_path(video_id)
    if not file_path or not file_path.is_file():
        return jsonify({"error": "Video file not found on disk."}), 404

    return send_file(
        str(file_path),
        mimetype="video/mp4",
        as_attachment=False,
        download_name=file_path.name
    )


@videos_bp.route("/<video_id>/thumbnail", methods=["GET"])
def serve_video_thumbnail(video_id: str):
    """Serve the JPEG thumbnail for a video."""
    manager = _get_video_manager()
    thumb_path = manager.get_thumbnail_file_path(video_id)
    if not thumb_path or not thumb_path.is_file():
        return jsonify({"error": "Thumbnail not found on disk."}), 404

    return send_file(
        str(thumb_path),
        mimetype="image/jpeg",
        as_attachment=False,
        download_name=thumb_path.name
    )


@videos_bp.route("/<video_id>/cancel", methods=["POST"])
@videos_bp.route("/jobs/<video_id>/cancel", methods=["POST"])
def cancel_video(video_id: str):
    """Cancel a running or queued video job."""
    manager = _get_video_manager()
    success = manager.cancel_job(video_id)
    if not success:
        return jsonify({"error": f"Could not cancel job '{video_id}' (not found or already completed)."}), 400

    return jsonify({
        "status": "success",
        "message": f"Video generation job '{video_id}' was cancelled."
    }), 200


@videos_bp.route("/<video_id>/regenerate", methods=["POST"])
def regenerate_video(video_id: str):
    """Regenerate a video asset from its original prompt."""
    manager = _get_video_manager()
    try:
        new_job = manager.regenerate(video_id)
        return jsonify({
            "status": "queued",
            "message": "Video regeneration queued successfully.",
            "generation_id": new_job.generation_id,
            "job": new_job.to_dict()
        }), 202
    except VideoNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@videos_bp.route("/<video_id>", methods=["DELETE"])
def delete_video(video_id: str):
    """Delete a video file, thumbnail, and history record."""
    manager = _get_video_manager()
    success = manager.delete_video(video_id)
    if not success:
        return jsonify({"error": f"Video '{video_id}' not found or could not be deleted."}), 404

    return jsonify({
        "status": "success",
        "message": f"Video '{video_id}' deleted successfully."
    }), 200


@videos_bp.route("/status", methods=["GET"])
def video_status():
    """Retrieve overall video generation subsystem diagnostics."""
    manager = _get_video_manager()
    return jsonify(manager.get_status()), 200


@videos_bp.route("/providers", methods=["GET"])
def video_providers():
    """Retrieve safe provider readiness details."""
    manager = _get_video_manager()
    return jsonify(manager.get_provider_status()), 200


@videos_bp.route("/local-capability", methods=["GET"])
def local_capability():
    """Retrieve host machine hardware report for local generation."""
    manager = _get_video_manager()
    report = manager.provider.check_health() if manager.provider.provider_name == "local" else None
    from video_generation.local_provider import detect_local_hardware
    return jsonify(detect_local_hardware().to_dict()), 200
