"""
Cloud Image Generation Provider for TONY AI (Stage 6).
Integrates with OpenAI DALL-E (or compatible image APIs) via REST.
Ensures zero API key leakage in logs, headers, or exception messages.
"""
import base64
import logging
import time
from typing import Tuple, Dict, Any
import requests
from image_generation.base import BaseImageProvider
from image_generation.models import ImageGenerationRequest
from image_generation.errors import (
    ImageGenerationError,
    ProviderUnavailableError,
    SafetyViolationError,
    RateLimitExceededError
)

logger = logging.getLogger("tony.image_generation.cloud")


class OpenAIImageProvider(BaseImageProvider):
    """OpenAI DALL-E Image Generation Provider."""

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "dall-e-3",
        base_url: str = "https://api.openai.com/v1",
        timeout: int = 60
    ):
        super().__init__(provider_name="openai", model_name=model_name)
        self.api_key = api_key.strip() if api_key else ""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def check_health(self) -> Dict[str, Any]:
        has_key = bool(self.api_key)
        return {
            "available": has_key,
            "provider": self.provider_name,
            "model": self.model_name,
            "status": "ready" if has_key else "missing_api_key",
            "base_url": self.base_url
        }

    def generate_image(self, request: ImageGenerationRequest) -> Tuple[bytes, Dict[str, Any]]:
        if not self.api_key:
            raise ProviderUnavailableError("OpenAI API key is missing. Set IMAGE_API_KEY or use Mock provider.")

        url = f"{self.base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # DALL-E 3 supports 1024x1024, 1024x1792, 1792x1024
        # Standardize size string
        size_str = "1024x1024"
        if request.width > request.height:
            size_str = "1792x1024" if self.model_name == "dall-e-3" else "1024x1024"
        elif request.height > request.width:
            size_str = "1024x1792" if self.model_name == "dall-e-3" else "1024x1024"

        payload = {
            "model": self.model_name,
            "prompt": request.prompt,
            "n": 1,
            "size": size_str,
            "response_format": "b64_json"
        }

        t_start = time.time()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        except requests.exceptions.Timeout:
            raise ImageGenerationError("Cloud image generation timed out.", status_code=504)
        except requests.exceptions.RequestException as e:
            logger.error("Network error during cloud image generation")
            raise ImageGenerationError("Network error connecting to image generation service.", status_code=503)

        elapsed_ms = int((time.time() - t_start) * 1000)

        # Handle HTTP error codes safely
        if resp.status_code == 401:
            raise ProviderUnavailableError("Cloud image API key is invalid or unauthorized.")
        elif resp.status_code == 429:
            raise RateLimitExceededError("Cloud image API rate limit exceeded.")
        elif resp.status_code == 400:
            err_data = resp.json().get("error", {}) if resp.text else {}
            err_msg = err_data.get("message", "Invalid image request.")
            if "safety" in err_msg.lower() or "policy" in err_msg.lower():
                raise SafetyViolationError(f"Cloud provider safety filter triggered: {err_msg}")
            raise ImageGenerationError(f"Cloud provider rejected request: {err_msg}", status_code=400)
        elif resp.status_code != 200:
            raise ImageGenerationError(f"Cloud provider returned error (HTTP {resp.status_code}).", status_code=resp.status_code)

        try:
            data = resp.json()
            item = data["data"][0]
            b64_img = item.get("b64_json")
            if b64_img:
                image_bytes = base64.b64decode(b64_img)
            elif "url" in item:
                # Fetch image from URL
                img_resp = requests.get(item["url"], timeout=30)
                image_bytes = img_resp.content
            else:
                raise ImageGenerationError("Provider response contained no image data.")

            revised_prompt = item.get("revised_prompt", request.prompt)
            metadata = {
                "provider": self.provider_name,
                "model": self.model_name,
                "revised_prompt": revised_prompt,
                "generation_time_ms": elapsed_ms,
                "simulated": False
            }
            return image_bytes, metadata

        except Exception as e:
            if isinstance(e, ImageGenerationError):
                raise
            logger.exception("Failed to parse cloud image provider response")
            raise ImageGenerationError("Failed to decode response from cloud image provider.")
