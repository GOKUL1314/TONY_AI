"""
Central Orchestrator for TONY AI Vision Subsystem (Stage 9).
Coordinates uploads, image validation, provider dispatch, active-image context,
and untrusted content tagging.
"""
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from vision.base import BaseVisionProvider
from vision.storage import VisionStorage
from vision.history import VisionHistoryManager
from vision.models import VisionAnalysisRequest, VisionResult, VisionTaskType
from vision.errors import VisionError, ImageNotFoundError, ImageValidationError

logger = logging.getLogger("tony.vision.manager")


class VisionManager:
    """Manages all image understanding operations for TONY AI."""

    def __init__(
        self,
        provider: BaseVisionProvider,
        storage: VisionStorage,
        history: VisionHistoryManager,
        image_manager=None
    ):
        self.provider = provider
        self.storage = storage
        self.history = history
        self.image_manager = image_manager
        self._active_vision_id: Optional[str] = None

    @property
    def active_vision_id(self) -> Optional[str]:
        return self._active_vision_id

    def set_active_vision_id(self, vision_id: Optional[str]) -> None:
        self._active_vision_id = vision_id

    def resolve_image(
        self,
        image_bytes: Optional[bytes] = None,
        image_id: Optional[str] = None,
        use_active: bool = False
    ) -> Tuple[bytes, Optional[str], Optional[Path]]:
        """
        Resolve raw bytes, identifier, and path from an upload, stored ID, or active context.
        """
        # Case 1: Use active generated image from Stage 6
        if use_active or (not image_bytes and not image_id):
            if not self.image_manager:
                raise ImageNotFoundError("No Image Manager is available to resolve active generated images.")
            active_record = self.image_manager.get_active_image()
            if not active_record or not active_record.file_path:
                raise ImageNotFoundError("No active generated image is available in conversational context.")
            path = Path(active_record.file_path)
            if not path.is_file():
                raise ImageNotFoundError(f"Active image file not found on disk: {path}")
            return path.read_bytes(), active_record.image_id, path

        # Case 2: Direct image bytes supplied
        if image_bytes:
            return image_bytes, image_id, None

        # Case 3: Image ID referencing an uploaded image or generated image
        if image_id:
            # Check vision storage first
            p = self.storage.get_image_path(image_id)
            if p and p.is_file():
                return p.read_bytes(), image_id, p

            # Check generated images via image_manager if available
            if self.image_manager:
                gen_rec = self.image_manager.history.get_record(image_id)
                if gen_rec and gen_rec.file_path and Path(gen_rec.file_path).is_file():
                    p_gen = Path(gen_rec.file_path)
                    return p_gen.read_bytes(), image_id, p_gen

            raise ImageNotFoundError(f"Image ID '{image_id}' could not be resolved in vision or generated storage.")

        raise ImageValidationError("No valid image source provided for visual analysis.")

    def analyze(
        self,
        image_bytes: Optional[bytes] = None,
        image_id: Optional[str] = None,
        prompt: str = "",
        task: VisionTaskType = VisionTaskType.ANALYZE,
        use_active: bool = False,
        original_filename: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 500
    ) -> VisionResult:
        """
        Execute visual analysis on an image.
        """
        # If new upload bytes are passed without an ID, save them safely first
        saved_id = image_id
        saved_path = None
        saved_filename = None

        if image_bytes and not image_id and not use_active:
            saved_id, saved_filename, saved_path, _ = self.storage.save_upload(
                image_bytes=image_bytes,
                original_filename=original_filename
            )

        resolved_bytes, effective_id, resolved_path = self.resolve_image(
            image_bytes=image_bytes,
            image_id=saved_id or image_id,
            use_active=use_active
        )

        request = VisionAnalysisRequest(
            image_bytes=resolved_bytes,
            image_path=resolved_path or saved_path,
            image_id=effective_id,
            prompt=prompt,
            task=task,
            temperature=temperature,
            max_tokens=max_tokens
        )

        # Dispatch to provider
        result = self.provider.analyze(request)
        result.image_id = effective_id
        result.image_filename = saved_filename or (resolved_path.name if resolved_path else None)
        result.file_path = str(resolved_path or saved_path) if (resolved_path or saved_path) else None

        # UNTRUSTED CONTENT GATE: Tag metadata to protect downstream tool execution
        result.metadata["untrusted_content"] = True
        result.metadata["source"] = "active_image" if use_active else "upload"

        # Record in history and update active vision context
        self.history.add_record(result)
        self._active_vision_id = result.vision_id
        return result

    def ask_question(
        self,
        question: str,
        image_bytes: Optional[bytes] = None,
        image_id: Optional[str] = None,
        use_active: bool = False
    ) -> VisionResult:
        """Ask a specific question about an image."""
        return self.analyze(
            image_bytes=image_bytes,
            image_id=image_id,
            prompt=question,
            task=VisionTaskType.QUESTION,
            use_active=use_active
        )

    def extract_text(
        self,
        image_bytes: Optional[bytes] = None,
        image_id: Optional[str] = None,
        use_active: bool = False
    ) -> VisionResult:
        """Extract or read visible text from an image (OCR)."""
        return self.analyze(
            image_bytes=image_bytes,
            image_id=image_id,
            prompt="Read and transcribe all visible text in this image accurately.",
            task=VisionTaskType.OCR,
            use_active=use_active
        )

    def describe(
        self,
        image_bytes: Optional[bytes] = None,
        image_id: Optional[str] = None,
        use_active: bool = False
    ) -> VisionResult:
        """Generate a detailed description of the image scene."""
        return self.analyze(
            image_bytes=image_bytes,
            image_id=image_id,
            prompt="Describe this image in detail, including key objects, composition, and colors.",
            task=VisionTaskType.DESCRIBE,
            use_active=use_active
        )

    def analyze_active_image(self, prompt: str = "", task: VisionTaskType = VisionTaskType.ANALYZE) -> VisionResult:
        """Direct helper to analyze the currently active generated image."""
        return self.analyze(
            prompt=prompt,
            task=task,
            use_active=True
        )

    def get_result(self, vision_id: str) -> Optional[VisionResult]:
        """Fetch result from history."""
        return self.history.get_record(vision_id)

    def list_history(self, limit: int = 50) -> List[VisionResult]:
        """List past vision results."""
        return self.history.list_records(limit=limit)

    def check_health(self) -> Dict[str, Any]:
        """Health check for vision subsystem."""
        provider_health = self.provider.check_health()
        return {
            "status": "healthy" if provider_health.get("available") else "degraded",
            "provider": provider_health,
            "storage_dir": str(self.storage.storage_dir),
            "stored_uploads_count": len(self.storage.list_images()),
            "history_count": len(self.history.list_records(limit=100))
        }
