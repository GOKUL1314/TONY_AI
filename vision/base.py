"""
Abstract Base Class for Vision Providers in TONY AI (Stage 9).
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from vision.models import VisionAnalysisRequest, VisionResult


class BaseVisionProvider(ABC):
    """Abstract interface that all TONY vision inference backends must implement."""

    def __init__(self, provider_name: str, model_name: str):
        self.provider_name = provider_name
        self.model_name = model_name

    @abstractmethod
    def analyze(self, request: VisionAnalysisRequest) -> VisionResult:
        """
        Perform visual analysis or question answering on an image.

        :param request: VisionAnalysisRequest containing image bytes/path, prompt, and task type.
        :return: VisionResult with description or answer, timing, and metadata.
        :raises VisionError: If analysis fails.
        """
        pass

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """
        Check health and readiness of the vision provider.

        :return: Dict containing health status, provider name, model, and availability.
        """
        pass
