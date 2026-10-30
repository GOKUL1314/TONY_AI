"""
Mock Vision Provider for TONY AI (Stage 9).
Provides deterministic simulation of vision analysis for unit tests and offline CI.
"""
import uuid
import time
from typing import Dict, Any
from vision.base import BaseVisionProvider
from vision.models import VisionAnalysisRequest, VisionResult, VisionTaskType
from vision.errors import VisionProviderError, VisionTimeoutError


class MockVisionProvider(BaseVisionProvider):
    """Simulated vision provider for fast testing without GPU/CPU heavy model execution."""

    def __init__(
        self,
        provider_name: str = "mock",
        model_name: str = "mock-vision-v1",
        simulate_latency: float = 0.0,
        force_error: bool = False,
        force_timeout: bool = False
    ):
        super().__init__(provider_name=provider_name, model_name=model_name)
        self.simulate_latency = simulate_latency
        self.force_error = force_error
        self.force_timeout = force_timeout

    def analyze(self, request: VisionAnalysisRequest) -> VisionResult:
        if self.simulate_latency > 0:
            time.sleep(self.simulate_latency)

        if self.force_timeout:
            raise VisionTimeoutError(f"Mock vision inference timed out after {self.simulate_latency}s.")

        if self.force_error:
            raise VisionProviderError("Simulated mock vision provider error.")

        task_val = request.task.value if isinstance(request.task, VisionTaskType) else str(request.task)
        prompt_lower = (request.prompt or "").lower()

        # Deterministic responses depending on task or prompt
        if task_val == VisionTaskType.OCR.value or "text" in prompt_lower or "ocr" in prompt_lower or "read" in prompt_lower:
            reply = "Detected text: 'TONY AI - SYSTEM READY'."
        elif "building" in prompt_lower or "skyline" in prompt_lower:
            reply = "The image shows a futuristic urban cityscape with towering modern skyscrapers and warm atmospheric lighting."
        elif "car" in prompt_lower:
            reply = "There are no cars visible in this aerial cityscape perspective."
        elif task_val == VisionTaskType.QUESTION.value:
            reply = f"Regarding your question ('{request.prompt}'): The image portrays an expansive high-tech scene."
        else:
            reply = "The image depicts a high-resolution scene featuring detailed architectural elements and balanced lighting."

        return VisionResult(
            vision_id=f"vis_mock_{uuid.uuid4().hex[:8]}",
            provider=self.provider_name,
            model=self.model_name,
            task=task_val,
            prompt=request.prompt,
            response=reply,
            image_id=request.image_id,
            simulated=True,
            duration_seconds=self.simulate_latency,
            metadata={"mock": True}
        )

    def check_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy" if not self.force_error else "unhealthy",
            "provider": self.provider_name,
            "model": self.model_name,
            "available": not self.force_error,
            "simulated": True
        }
