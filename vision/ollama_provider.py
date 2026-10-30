"""
Ollama Local Vision Provider for TONY AI (Stage 9).
Integrates with locally running Ollama instance to analyze images using vision models like Moondream.
"""
import base64
import logging
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
import requests

from vision.base import BaseVisionProvider
from vision.models import VisionAnalysisRequest, VisionResult, VisionTaskType
from vision.errors import VisionProviderError, VisionTimeoutError, ImageValidationError

logger = logging.getLogger("tony.vision.ollama")


class OllamaVisionProvider(BaseVisionProvider):
    """Real local multimodal vision provider powered by Ollama."""

    def __init__(
        self,
        model_name: str = "moondream",
        base_url: str = "http://localhost:11434",
        timeout: int = 90
    ):
        super().__init__(provider_name="ollama", model_name=model_name)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def analyze(self, request: VisionAnalysisRequest) -> VisionResult:
        """
        Send image and prompt to Ollama /api/generate endpoint.
        """
        # 1. Resolve raw image bytes
        image_bytes = request.image_bytes
        if not image_bytes and request.image_path:
            p = Path(request.image_path)
            if not p.is_file():
                raise ImageValidationError(f"Target image path does not exist: {p}")
            image_bytes = p.read_bytes()

        if not image_bytes:
            raise ImageValidationError("Vision request did not supply valid image bytes or a readable file path.")

        # 2. Base64 encode image
        try:
            b64_image = base64.b64encode(image_bytes).decode("utf-8")
        except Exception as e:
            raise ImageValidationError(f"Failed to encode image to base64: {e}")

        # 3. Format prompt based on task
        task_str = request.task.value if isinstance(request.task, VisionTaskType) else str(request.task)
        prompt = request.prompt.strip() if request.prompt else ""
        if not prompt:
            if task_str == VisionTaskType.OCR.value:
                prompt = "Read and transcribe all visible text in this image accurately."
            elif task_str == VisionTaskType.DESCRIBE.value:
                prompt = "Describe this image in detail, including key objects, scene composition, and colors."
            else:
                prompt = "What is in this image? Provide a clear, structured overview."

        endpoint = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "images": [b64_image],
            "stream": False
        }
        if request.metadata and "options" in request.metadata:
            payload["options"] = request.metadata["options"]


        start_time = time.time()
        logger.info(f"Dispatching vision request to Ollama [{self.model_name}] at {endpoint}")

        try:
            response = requests.post(endpoint, json=payload, timeout=self.timeout)
            duration = time.time() - start_time

            if response.status_code == 404:
                raise VisionProviderError(
                    f"Vision model '{self.model_name}' was not found in your local Ollama library. "
                    f"Please pull the model using `ollama pull {self.model_name}`."
                )

            if response.status_code != 200:
                raise VisionProviderError(
                    f"Ollama vision endpoint returned HTTP {response.status_code}: {response.text}"
                )

            data = response.json()
            raw_text = data.get("response", "").strip()
            if not raw_text:
                raise VisionProviderError("Received an empty response from local Ollama vision model.")

            vision_id = f"vis_ollama_{uuid.uuid4().hex[:8]}"
            return VisionResult(
                vision_id=vision_id,
                provider=self.provider_name,
                model=self.model_name,
                task=task_str,
                prompt=prompt,
                response=raw_text,
                image_id=request.image_id,
                file_path=str(request.image_path) if request.image_path else None,
                simulated=False,
                duration_seconds=duration,
                metadata={
                    "total_duration": data.get("total_duration"),
                    "load_duration": data.get("load_duration"),
                    "eval_count": data.get("eval_count")
                }
            )

        except requests.exceptions.ConnectionError:
            err_msg = (
                f"Unable to connect to local Ollama server at {self.base_url}. "
                "Please verify that Ollama is running (`ollama serve`)."
            )
            logger.error(err_msg)
            raise VisionProviderError(err_msg)

        except requests.exceptions.Timeout:
            err_msg = f"Ollama vision model inference timed out after {self.timeout}s."
            logger.error(err_msg)
            raise VisionTimeoutError(err_msg)

        except requests.exceptions.RequestException as e:
            err_msg = f"Ollama HTTP communication failed: {str(e)}"
            logger.error(err_msg)
            raise VisionProviderError(err_msg)

    def check_health(self) -> Dict[str, Any]:
        """Check Ollama service status and verify whether the vision model is loaded."""
        tags_url = f"{self.base_url}/api/tags"
        try:
            res = requests.get(tags_url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                model_ready = any(self.model_name in m for m in models)
                return {
                    "status": "healthy" if model_ready else "model_missing",
                    "provider": self.provider_name,
                    "model": self.model_name,
                    "available": model_ready,
                    "installed_models": models,
                    "simulated": False
                }
            return {
                "status": f"http_{res.status_code}",
                "provider": self.provider_name,
                "model": self.model_name,
                "available": False,
                "simulated": False
            }
        except Exception as e:
            return {
                "status": "unreachable",
                "error": str(e),
                "provider": self.provider_name,
                "model": self.model_name,
                "available": False,
                "simulated": False
            }
