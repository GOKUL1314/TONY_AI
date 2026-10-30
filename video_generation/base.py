"""
Abstract Base Class for Video Generation Providers in TONY AI (Stage 7).
Defines the contract for Hugging Face, Local, and Mock video synthesis engines.
"""
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, Optional, Callable
from video_generation.models import VideoGenerationRequest


class VideoProvider(ABC):
    """Abstract interface that all TONY video generation backends must implement."""

    def __init__(
        self,
        provider_name: str,
        model_name: str,
        supports_text_to_video: bool = True,
        supports_image_to_video: bool = False,
        supports_cancellation: bool = False
    ):
        self.provider_name = provider_name
        self.model_name = model_name
        self.supports_text_to_video = supports_text_to_video
        self.supports_image_to_video = supports_image_to_video
        self.supports_cancellation = supports_cancellation

    @abstractmethod
    def generate_text_to_video(
        self,
        request: VideoGenerationRequest,
        progress_callback: Optional[Callable[[Optional[int], str], None]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a video from a text prompt.

        :param request: VideoGenerationRequest with prompt, duration, resolution, etc.
        :param progress_callback: Optional callback func(progress_pct_or_none, status_message)
        :return: Tuple of (raw_mp4_or_webm_bytes, metadata_dict)
        :raises VideoGenerationError: If generation fails.
        """
        pass

    @abstractmethod
    def generate_image_to_video(
        self,
        request: VideoGenerationRequest,
        image_bytes: bytes,
        progress_callback: Optional[Callable[[Optional[int], str], None]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Animate an existing static image into a video.

        :param request: VideoGenerationRequest.
        :param image_bytes: Raw image file bytes to animate.
        :param progress_callback: Optional callback.
        :return: Tuple of (raw_video_bytes, metadata_dict).
        :raises VideoGenerationError: If animation fails.
        """
        pass

    def cancel(self, generation_id: str) -> bool:
        """
        Attempt to cancel an in-flight video generation job on the backend.
        Default implementation returns False if provider cannot cancel remotely.
        """
        return False

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """
        Inspect health and capability readiness of the provider.

        :return: Dict containing health status, provider name, and availability.
        """
        pass
