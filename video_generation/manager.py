"""
Video Generation Manager for TONY AI (Stage 7).
Coordinates prompt validation, safety filters, asynchronous job dispatch,
storage, history, regeneration, and cross-stage image-to-video integration.
"""
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from video_generation.base import VideoProvider
from video_generation.storage import VideoStorage
from video_generation.history import VideoHistoryManager
from video_generation.jobs import VideoJobManager
from video_generation.models import (
    VideoGenerationRequest,
    VideoMetadata,
    VideoJob,
    VideoGenerationResult
)
from video_generation.safety import validate_prompt_or_raise, validate_safe_image_source
from video_generation.prompts import (
    detect_video_intent,
    enhance_video_prompt
)
from video_generation.errors import (
    VideoGenerationError,
    SafetyViolationError,
    VideoValidationError,
    VideoNotFoundError,
    UnsupportedVideoCapabilityError
)
from video_generation.local_provider import detect_local_hardware

logger = logging.getLogger("tony.video_generation.manager")


class VideoGenerationManager:
    """Central orchestrator for all video generation capabilities in TONY AI."""

    def __init__(
        self,
        provider: VideoProvider,
        storage: VideoStorage,
        history: VideoHistoryManager,
        job_manager: Optional[VideoJobManager] = None,
        image_manager: Optional[Any] = None,
        enhance_prompts: bool = True,
        default_duration: int = 5,
        max_duration: int = 5,
        default_width: int = 512,
        default_height: int = 512,
        default_fps: int = 16,
        allow_paid: bool = False
    ):
        self.provider = provider
        self.storage = storage
        self.history = history
        self.image_manager = image_manager
        self.enhance_prompts = enhance_prompts
        self.default_duration = default_duration
        self.max_duration = max_duration
        self.default_width = default_width
        self.default_height = default_height
        self.default_fps = default_fps
        self.allow_paid = allow_paid

        # Initialize internal job manager if not supplied
        if job_manager is not None:
            self.job_manager = job_manager
        else:
            self.job_manager = VideoJobManager(
                provider=self.provider,
                storage=self.storage,
                history=self.history
            )

        self._active_video_id: Optional[str] = None
        latest = self.history.get_latest_record()
        if latest:
            self._active_video_id = latest.video_id

    @property
    def active_video_id(self) -> Optional[str]:
        return self._active_video_id

    def set_active_video_id(self, video_id: Optional[str]) -> None:
        self._active_video_id = video_id

    def get_active_video(self) -> Optional[VideoMetadata]:
        """Retrieve metadata of the currently active video."""
        if self._active_video_id:
            rec = self.history.get_record(self._active_video_id)
            if rec:
                return rec
        return self.history.get_latest_record()

    def get_active_image(self) -> Optional[Any]:
        """Retrieve active image from Stage 6 ImageManager if wired."""
        if self.image_manager and hasattr(self.image_manager, "get_active_image"):
            return self.image_manager.get_active_image()
        return None

    def detect_intent(self, text: str) -> Dict[str, Any]:
        """Detect video intent from conversational text."""
        has_active = bool(self.get_active_image())
        return detect_video_intent(text, has_active_image=has_active)

    def start_text_to_video(
        self,
        prompt: str,
        duration: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
        enhance: Optional[bool] = None,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None
    ) -> VideoJob:
        """
        Validate, prepare, and queue a text-to-video generation job.
        """
        if not prompt or not prompt.strip():
            raise VideoValidationError("Video prompt cannot be empty.")

        # 1. Safety check
        clean_prompt = validate_prompt_or_raise(prompt)

        # 2. Duration limit check
        effective_duration = duration if duration is not None else self.default_duration
        if effective_duration > self.max_duration:
            raise VideoValidationError(
                f"The current video limit is {self.max_duration} seconds. Please request a duration of {self.max_duration} seconds or less."
            )
        if effective_duration <= 0:
            effective_duration = self.default_duration

        # 3. Prompt enhancement
        should_enhance = self.enhance_prompts if enhance is None else enhance
        effective_prompt = enhance_video_prompt(clean_prompt) if should_enhance else clean_prompt

        eff_width = width or self.default_width
        eff_height = height or self.default_height
        eff_fps = fps or self.default_fps

        request = VideoGenerationRequest(
            prompt=effective_prompt,
            duration=effective_duration,
            width=eff_width,
            height=eff_height,
            fps=eff_fps,
            enhance=should_enhance,
            seed=seed,
            negative_prompt=negative_prompt
        )

        job = self.job_manager.submit_job(request)
        self._active_video_id = job.generation_id
        return job

    def start_image_to_video(
        self,
        image_id: Optional[str] = None,
        prompt: Optional[str] = None,
        duration: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
        seed: Optional[int] = None
    ) -> VideoJob:
        """
        Validate, prepare, and queue an image-to-video animation job.
        """
        if not self.provider.supports_image_to_video:
            raise UnsupportedVideoCapabilityError(
                f"The active video provider '{self.provider.provider_name}' does not support image-to-video animation."
            )

        # Resolve image metadata
        target_image_meta = None
        if image_id and self.image_manager:
            target_image_meta = self.image_manager.get_image(image_id)
        elif self.image_manager:
            target_image_meta = self.image_manager.get_active_image()

        if not target_image_meta:
            raise VideoValidationError(
                "No active image is available to animate. Please generate or select an image first."
            )

        # Validate image file on disk
        img_path = Path(target_image_meta.file_path).resolve()
        if not img_path.is_file():
            raise VideoNotFoundError(f"Source image file '{img_path.name}' not found on disk.")

        # Read image bytes safely
        try:
            image_bytes = img_path.read_bytes()
        except OSError as e:
            raise VideoGenerationError(f"Could not read source image file: {e}")

        effective_prompt = prompt or target_image_meta.prompt or "cinematic animation of the image"
        clean_prompt = validate_prompt_or_raise(effective_prompt)

        effective_duration = duration if duration is not None else self.default_duration
        if effective_duration > self.max_duration:
            raise VideoValidationError(
                f"The current video limit is {self.max_duration} seconds. Please request {self.max_duration}s or less."
            )

        request = VideoGenerationRequest(
            prompt=clean_prompt,
            duration=effective_duration,
            width=width or target_image_meta.width or self.default_width,
            height=height or target_image_meta.height or self.default_height,
            fps=fps or self.default_fps,
            parent_image_id=target_image_meta.image_id,
            source_image_path=str(img_path),
            seed=seed
        )

        job = self.job_manager.submit_job(request, source_image_bytes=image_bytes)
        self._active_video_id = job.generation_id
        return job

    def get_job_status(self, generation_id: str) -> Optional[VideoJob]:
        """Look up job status by generation ID."""
        return self.job_manager.get_job(generation_id)

    def cancel_job(self, generation_id: str) -> bool:
        """Cancel an ongoing video generation job."""
        return self.job_manager.cancel_job(generation_id)

    def regenerate(self, video_id: str) -> VideoJob:
        """Regenerate a video asset using its original prompt and settings."""
        record = self.history.get_record(video_id)
        if not record:
            raise VideoNotFoundError(f"Video '{video_id}' not found in history.")

        return self.start_text_to_video(
            prompt=record.prompt,
            duration=record.duration,
            width=record.width,
            height=record.height,
            fps=record.fps
        )

    def get_video(self, video_id: str) -> Optional[VideoMetadata]:
        """Retrieve video metadata from history or completed job."""
        rec = self.history.get_record(video_id)
        if rec:
            return rec
        job = self.job_manager.get_job(video_id)
        if job and job.video_metadata:
            return job.video_metadata
        return None

    def get_video_file_path(self, video_id: str) -> Optional[Path]:
        """Retrieve local filesystem Path for a video asset."""
        video = self.get_video(video_id)
        if not video:
            return None
        return self.storage.get_video_path(video.filename)

    def get_thumbnail_file_path(self, video_id: str) -> Optional[Path]:
        """Retrieve local filesystem Path for a video thumbnail."""
        video = self.get_video(video_id)
        if not video or not video.thumbnail_path:
            return None
        tpath = Path(video.thumbnail_path)
        return self.storage.get_thumbnail_path(tpath.name)

    def list_videos(self, limit: int = 50, offset: int = 0) -> List[VideoMetadata]:
        """List paginated history of video assets."""
        return self.history.list_records(limit=limit, offset=offset)

    def delete_video(self, video_id: str) -> bool:
        """Delete video file, thumbnail, and history record."""
        video = self.get_video(video_id)
        if not video:
            return False

        tname = Path(video.thumbnail_path).name if video.thumbnail_path else None
        self.storage.delete_video_file(video.filename, thumb_filename=tname)
        deleted = self.history.delete_record(video_id)

        if self._active_video_id == video_id:
            latest = self.history.get_latest_record()
            self._active_video_id = latest.video_id if latest else None

        return deleted

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status for the Video Generation subsystem."""
        health = self.provider.check_health()
        local_report = detect_local_hardware()
        return {
            "status": "online" if health.get("available") else "degraded",
            "provider": self.provider.provider_name,
            "model": self.provider.model_name,
            "provider_available": health.get("available", False),
            "free_mode_active": not self.allow_paid,
            "paid_fallback_enabled": self.allow_paid,
            "total_videos_recorded": self.history.count(),
            "active_video_id": self._active_video_id,
            "supports_image_to_video": self.provider.supports_image_to_video,
            "max_duration_seconds": self.max_duration,
            "local_capability": local_report.to_dict()
        }

    def get_provider_status(self) -> Dict[str, Any]:
        """Return safe provider availability details without secret disclosure."""
        local_report = detect_local_hardware()
        hf_token_set = False
        hf_available = False

        if isinstance(self.provider, VideoProvider) and self.provider.provider_name == "huggingface":
            hf_status = self.provider.check_health()
            hf_token_set = hf_status.get("token_configured", False)
            hf_available = hf_status.get("available", False)

        return {
            "huggingface": {
                "configured": hf_token_set,
                "available": hf_available,
                "paid_fallback": self.allow_paid,
                "mode": "free_allowance"
            },
            "local": {
                "configured": local_report.local_model_configured,
                "available": local_report.provider_available,
                "gpu": local_report.gpu_name,
                "cuda": local_report.cuda_available,
                "reason": local_report.reason
            },
            "mock": {
                "available": True,
                "simulated": True
            },
            "active_provider": self.provider.provider_name,
            "free_safe_mode": not self.allow_paid
        }
