"""
Image Generation Manager orchestrator for TONY AI (Stage 6).
Coordinates intent detection, prompt safety, provider dispatch, disk storage,
history tracking, and conversational follow-up edit context.
"""
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from image_generation.base import BaseImageProvider
from image_generation.storage import ImageStorage
from image_generation.history import ImageHistoryManager
from image_generation.models import (
    ImageGenerationRequest,
    ImageMetadata,
    ImageGenerationResult
)
from image_generation.errors import (
    ImageGenerationError,
    SafetyViolationError,
    InvalidPromptError,
    ImageNotFoundError,
    ProviderUnavailableError
)
from image_generation.safety import validate_prompt_or_raise
from image_generation.prompts import (
    detect_image_intent,
    merge_edit_prompt,
    enhance_prompt
)

logger = logging.getLogger("tony.image_generation.manager")


class ImageGenerationManager:
    """Central orchestrator for all image generation capabilities in TONY AI."""

    def __init__(
        self,
        provider: BaseImageProvider,
        storage: ImageStorage,
        history: ImageHistoryManager,
        enhance_prompts: bool = True,
        fallback_provider: Optional[BaseImageProvider] = None
    ):
        self.provider = provider
        self.fallback_provider = fallback_provider
        self.storage = storage
        self.history = history
        self.enhance_prompts = enhance_prompts
        self._active_image_id: Optional[str] = None

        # Seed active image id from most recent record if available
        latest = self.history.get_latest_record()
        if latest:
            self._active_image_id = latest.image_id

    @property
    def active_image_id(self) -> Optional[str]:
        return self._active_image_id

    def set_active_image_id(self, image_id: Optional[str]) -> None:
        self._active_image_id = image_id

    def get_active_image(self) -> Optional[ImageMetadata]:
        if self._active_image_id:
            record = self.history.get_record(self._active_image_id)
            if record:
                return record
        return self.history.get_latest_record()

    def detect_intent(self, text: str) -> Dict[str, Any]:
        """Detect image generation, edit, or regeneration intent from conversational text."""
        has_active = bool(self.get_active_image())
        return detect_image_intent(text, has_active_image=has_active)

    def generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        parent_image_id: Optional[str] = None,
        enhance: Optional[bool] = None
    ) -> ImageGenerationResult:
        """
        Generate a new image from a prompt.

        :param prompt: User prompt describing the image.
        :param width: Image width in pixels.
        :param height: Image height in pixels.
        :param parent_image_id: Optional parent image ID if derived or edited.
        :param enhance: Whether to apply aesthetic prompt enhancement.
        :return: ImageGenerationResult with status and metadata.
        """
        try:
            # 1. Prompt validation & safety filter
            if not prompt or not prompt.strip():
                raise InvalidPromptError("Prompt cannot be empty.")
            clean_prompt = validate_prompt_or_raise(prompt)

            # 2. Optional prompt enhancement
            should_enhance = self.enhance_prompts if enhance is None else enhance
            effective_prompt = enhance_prompt(clean_prompt) if should_enhance else clean_prompt

            request = ImageGenerationRequest(
                prompt=effective_prompt,
                width=width,
                height=height,
                parent_image_id=parent_image_id,
                enhance=should_enhance
            )

            # 3. Invoke provider with fallback support
            logger.info(f"Generating image via {self.provider.provider_name} [{self.provider.model_name}]...")
            active_provider = self.provider
            try:
                image_bytes, meta = self.provider.generate_image(request)
            except ProviderUnavailableError as pue:
                if self.fallback_provider:
                    logger.info(
                        f"Primary image provider '{self.provider.provider_name}' unavailable ({pue}). "
                        f"Engaging fallback provider '{self.fallback_provider.provider_name}' [{self.fallback_provider.model_name}]..."
                    )
                    active_provider = self.fallback_provider
                    image_bytes, meta = self.fallback_provider.generate_image(request)
                else:
                    raise

            # 4. Save to local storage
            fmt = meta.get("format", "png")
            width_val = meta.get("width", width)
            height_val = meta.get("height", height)
            sim_val = meta.get("simulated", active_provider.provider_name == "mock")
            ext = "jpg" if fmt in ("jpeg", "jpg") else ("webp" if fmt == "webp" else "png")

            image_id, filename, file_path, file_size = self.storage.save_image_bytes(image_bytes, ext=ext)

            # 5. Build metadata object
            url_path = f"/api/images/{image_id}/file"
            metadata = ImageMetadata(
                image_id=image_id,
                filename=filename,
                file_path=str(file_path),
                url=url_path,
                prompt=clean_prompt,
                revised_prompt=meta.get("revised_prompt", effective_prompt),
                width=width_val,
                height=height_val,
                format=fmt,
                parent_image_id=parent_image_id,
                provider=active_provider.provider_name,
                model=active_provider.model_name,
                generation_time_ms=meta.get("generation_time_ms", 0),
                file_size_bytes=file_size,
                simulated=sim_val
            )

            # 6. Record in persistent history & update active image context
            self.history.add_record(metadata)
            self._active_image_id = image_id

            logger.info(f"Generated image '{image_id}' saved successfully ({file_size} bytes).")
            return ImageGenerationResult(
                success=True,
                image_metadata=metadata,
                status_code=200
            )

        except SafetyViolationError as e:
            logger.warning(f"Image generation safety rejection: {e.message}")
            return ImageGenerationResult(
                success=False,
                error_message=e.message,
                status_code=e.status_code
            )
        except ImageGenerationError as e:
            logger.error(f"Image generation error: {e.message}")
            return ImageGenerationResult(
                success=False,
                error_message=e.message,
                status_code=e.status_code
            )
        except Exception as e:
            logger.exception(f"Unexpected error during image generation: {e}")
            return ImageGenerationResult(
                success=False,
                error_message=f"An unexpected error occurred: {str(e)}",
                status_code=500
            )

    def edit(
        self,
        instruction: str,
        image_id: Optional[str] = None,
        width: int = 1024,
        height: int = 1024
    ) -> ImageGenerationResult:
        """
        Edit or refine a previous image based on natural language instructions.
        """
        target_id = image_id or self._active_image_id
        target_record = self.history.get_record(target_id) if target_id else self.history.get_latest_record()

        if not target_record:
            return ImageGenerationResult(
                success=False,
                error_message="No previous image found to edit. Please create an image first.",
                status_code=404
            )

        # Merge original prompt with the new edit instruction
        new_prompt = merge_edit_prompt(target_record.prompt, instruction)
        logger.info(f"Refining image {target_record.image_id} with prompt: '{new_prompt}'")

        return self.generate(
            prompt=new_prompt,
            width=width,
            height=height,
            parent_image_id=target_record.image_id,
            enhance=False
        )

    def regenerate(self, image_id: Optional[str] = None) -> ImageGenerationResult:
        """
        Regenerate the image using the same prompt.
        """
        target_id = image_id or self._active_image_id
        target_record = self.history.get_record(target_id) if target_id else self.history.get_latest_record()

        if not target_record:
            return ImageGenerationResult(
                success=False,
                error_message="No previous image found to regenerate. Please create an image first.",
                status_code=404
            )

        logger.info(f"Regenerating image {target_record.image_id} with prompt: '{target_record.prompt}'")
        return self.generate(
            prompt=target_record.prompt,
            width=target_record.width,
            height=target_record.height,
            parent_image_id=target_record.image_id,
            enhance=False
        )

    def get_image(self, image_id: str) -> Optional[ImageMetadata]:
        """Retrieve metadata for an image by ID."""
        return self.history.get_record(image_id)

    def get_image_file_path(self, image_id: str) -> Optional[Path]:
        """Locate physical file path for an image by ID."""
        record = self.get_image(image_id)
        if not record:
            return None
        return self.storage.get_image_path(record.filename)

    def list_images(self, limit: int = 50, offset: int = 0) -> List[ImageMetadata]:
        """List generated images with pagination."""
        return self.history.list_records(limit=limit, offset=offset)

    def delete_image(self, image_id: str) -> bool:
        """Delete an image from disk and metadata history."""
        record = self.get_image(image_id)
        if not record:
            return False

        # Remove physical file
        self.storage.delete_image_file(record.filename)
        # Remove metadata record
        deleted = self.history.delete_record(image_id)

        # Clear active image if deleted
        if self._active_image_id == image_id:
            latest = self.history.get_latest_record()
            self._active_image_id = latest.image_id if latest else None

        return deleted

    def get_status(self) -> Dict[str, Any]:
        """Diagnostic status of the image generation subsystem."""
        health = self.provider.check_health()
        return {
            "subsystem": "image_generation",
            "stage": 6,
            "status": "ready" if health.get("available") else "degraded",
            "provider": health,
            "total_images": self.history.count(),
            "active_image_id": self._active_image_id,
            "storage_dir": str(self.storage.storage_dir)
        }
