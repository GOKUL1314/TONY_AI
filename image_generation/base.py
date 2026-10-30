"""
Abstract Base Class for Image Generation Providers in TONY AI (Stage 6).
"""
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any
from image_generation.models import ImageGenerationRequest


class BaseImageProvider(ABC):
    """Abstract interface that all TONY image generation backends must implement."""

    def __init__(self, provider_name: str, model_name: str):
        self.provider_name = provider_name
        self.model_name = model_name

    @abstractmethod
    def generate_image(self, request: ImageGenerationRequest) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate an image given a request.

        :param request: ImageGenerationRequest containing prompt, dimensions, etc.
        :return: Tuple of (raw_png_bytes, metadata_dict)
        :raises ImageGenerationError: If generation fails.
        """
        pass

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """
        Check health and readiness of the provider.

        :return: Dict containing health status, provider name, and availability.
        """
        pass
