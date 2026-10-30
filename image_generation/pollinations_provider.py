"""
Pollinations.ai Free-First Image Generation Provider for TONY AI (Stage 6).
Provides free, high-quality, zero-configuration text-to-image synthesis using FLUX and SDXL.
Does not require API keys, payment methods, or user accounts.
"""
import logging
import struct
import time
import urllib.parse
from typing import Tuple, Dict, Any, Optional
import requests
from image_generation.base import BaseImageProvider
from image_generation.models import ImageGenerationRequest
from image_generation.errors import (
    ImageGenerationError,
    ProviderUnavailableError,
    RateLimitExceededError,
    InvalidPromptError,
    SafetyViolationError
)

logger = logging.getLogger("tony.image_generation.pollinations")

# Maximum permitted response body size (25 MB)
MAX_IMAGE_RESPONSE_BYTES = 25 * 1024 * 1024


def parse_jpeg_dimensions(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse (width, height) from raw JPEG byte buffer using SOF markers (pure Python).
    """
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None, None

    i = 2
    data_len = len(data)
    while i < data_len - 8:
        if data[i] != 0xFF:
            i += 1
            continue

        marker = data[i + 1]
        # Ignore standalone markers (RST, SOI, EOI)
        if marker in (0xD8, 0xD9, 0x00) or (0xD0 <= marker <= 0xD7):
            i += 2
            continue

        if i + 4 > data_len:
            break

        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        # SOF0 (Baseline), SOF1 (Extended Sequential), SOF2 (Progressive)
        if marker in (0xC0, 0xC1, 0xC2):
            if i + 9 <= data_len:
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h

        i += 2 + length

    return None, None


def parse_png_dimensions(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse (width, height) from raw PNG IHDR chunk (pure Python).
    """
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    return None, None


def detect_image_format_and_dimensions(data: bytes) -> Tuple[str, Optional[int], Optional[int]]:
    """
    Validate binary image magic bytes and extract dimensions.
    Returns (format_str, width, height).
    """
    if data.startswith(b"\xff\xd8\xff"):
        w, h = parse_jpeg_dimensions(data)
        return "jpeg", w, h
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        w, h = parse_png_dimensions(data)
        return "png", w, h
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "webp", None, None
    return "unknown", None, None


class PollinationsImageProvider(BaseImageProvider):
    """
    Free-first, zero-configuration Image Generation Provider utilizing Pollinations.ai.
    Generates photorealistic images via open FLUX.1 and SDXL models without credentials.
    """

    def __init__(
        self,
        model_name: str = "sana",
        base_url: str = "https://image.pollinations.ai",
        timeout: int = 60,
        max_response_size: int = MAX_IMAGE_RESPONSE_BYTES,
        max_retries: int = 2
    ):
        super().__init__(provider_name="pollinations", model_name=model_name or "sana")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_response_size = max_response_size
        self.max_retries = max_retries

    def check_health(self) -> Dict[str, Any]:
        """
        Check health and configuration status of the Pollinations provider.
        """
        return {
            "available": True,
            "provider": self.provider_name,
            "model": self.model_name,
            "status": "ready",
            "base_url": self.base_url,
            "simulated": False
        }

    def generate_image(self, request: ImageGenerationRequest) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a real image using Pollinations.ai API.

        :param request: ImageGenerationRequest containing prompt, dimensions, etc.
        :return: Tuple of (raw_image_bytes, metadata_dict)
        :raises InvalidPromptError: If prompt is empty.
        :raises RateLimitExceededError: If HTTP 429 received.
        :raises ProviderUnavailableError: If service is down or network unreachable.
        :raises ImageGenerationError: On invalid parameters, non-image response, or server error.
        """
        if not request.prompt or not request.prompt.strip():
            raise InvalidPromptError("Image prompt cannot be empty.")

        clean_prompt = request.prompt.strip()
        encoded_prompt = urllib.parse.quote(clean_prompt)
        target_url = f"{self.base_url}/prompt/{encoded_prompt}"

        # Standardize dimensions
        width = max(64, min(int(request.width or 1024), 2048))
        height = max(64, min(int(request.height or 1024), 2048))

        params: Dict[str, Any] = {
            "model": self.model_name,
            "width": width,
            "height": height,
            "nologo": "true"
        }

        # Optional seed if provided
        seed = request.provider_params.get("seed")
        if seed is not None:
            params["seed"] = seed

        headers = {
            "User-Agent": "TONY-AI/1.0 (Desktop Assistant; Windows)",
            "Accept": "image/jpeg, image/png, image/*"
        }

        logger.info(
            f"Dispatching Pollinations request for prompt='{clean_prompt[:50]}...' "
            f"[Model: {self.model_name}, Dimensions: {width}x{height}]"
        )

        t_start = time.time()
        resp = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.get(
                    target_url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )
            except requests.exceptions.Timeout:
                elapsed_ms = int((time.time() - t_start) * 1000)
                logger.warning(f"Pollinations request timed out (attempt {attempt + 1}/{self.max_retries + 1}) [Elapsed: {elapsed_ms}ms].")
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                logger.error(f"Pollinations request timed out after {self.timeout}s.")
                raise ImageGenerationError("Pollinations image generation timed out.", status_code=504)
            except requests.exceptions.ConnectionError as ce:
                elapsed_ms = int((time.time() - t_start) * 1000)
                logger.warning(f"Pollinations connection error (attempt {attempt + 1}/{self.max_retries + 1}): {ce} [Elapsed: {elapsed_ms}ms].")
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                logger.error(f"Pollinations connection error: {ce}")
                raise ProviderUnavailableError("Network connection error reaching Pollinations service.")
            except requests.exceptions.RequestException as re:
                elapsed_ms = int((time.time() - t_start) * 1000)
                logger.error(f"Pollinations communication error: {re} [Elapsed: {elapsed_ms}ms]")
                raise ImageGenerationError("Failed to communicate with Pollinations service.", status_code=503)

            # Check for content filtering / safety policy rejection in response body
            body_preview = resp.text[:500].lower() if resp.text else ""
            if any(term in body_preview for term in ("nsfw", "content filter", "policy violation", "prohibited content", "flagged")):
                logger.warning("Pollinations indicated content policy violation in response.")
                raise SafetyViolationError("Pollinations rejected the image request due to content policy.")

            # Inspect HTTP status codes
            if resp.status_code == 200:
                break
            elif resp.status_code == 429:
                logger.warning(f"Pollinations rate limit exceeded (HTTP 429, attempt {attempt + 1}/{self.max_retries + 1}).")
                if attempt < self.max_retries:
                    time.sleep(2.0)
                    continue
                raise RateLimitExceededError("Pollinations image generation rate limit exceeded. Please wait a moment.")
            elif resp.status_code in (500, 502, 503, 504):
                logger.warning(f"Pollinations server error (HTTP {resp.status_code}, attempt {attempt + 1}/{self.max_retries + 1}).")
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                elapsed_ms = int((time.time() - t_start) * 1000)
                logger.error(
                    f"Pollinations image generation failed [Provider: {self.provider_name}, "
                    f"Model: {self.model_name}, HTTP Status: {resp.status_code}, Elapsed: {elapsed_ms}ms, "
                    f"Retries: {attempt}]"
                )
                raise ProviderUnavailableError(
                    f"Pollinations service is temporarily unavailable (HTTP {resp.status_code}).",
                    status_code=resp.status_code
                )
            elif resp.status_code == 402:
                logger.error("Pollinations returned HTTP 402 Payment Required for model.")
                raise ImageGenerationError(
                    f"Pollinations returned HTTP 402 Payment Required for model '{self.model_name}'. "
                    "Use the free model 'sana' for zero-cost generation.",
                    status_code=402
                )
            elif resp.status_code == 400:
                logger.warning("Pollinations rejected request parameters (HTTP 400).")
                raise ImageGenerationError("Pollinations rejected the image request parameters.", status_code=400)
            else:
                elapsed_ms = int((time.time() - t_start) * 1000)
                logger.error(
                    f"Pollinations returned unexpected HTTP status {resp.status_code} "
                    f"[Provider: {self.provider_name}, Model: {self.model_name}, Elapsed: {elapsed_ms}ms]"
                )
                raise ImageGenerationError(f"Pollinations returned HTTP {resp.status_code}.", status_code=resp.status_code)

        elapsed_ms = int((time.time() - t_start) * 1000)

        # 2. Maximum response size protection
        content_length_hdr = resp.headers.get("Content-Length")
        if content_length_hdr and content_length_hdr.isdigit():
            if int(content_length_hdr) > self.max_response_size:
                raise ImageGenerationError(
                    f"Pollinations response exceeded maximum allowed size ({content_length_hdr} bytes).",
                    status_code=502
                )

        raw_bytes = resp.content
        if len(raw_bytes) > self.max_response_size:
            raise ImageGenerationError(
                f"Pollinations response exceeded maximum allowed size ({len(raw_bytes)} bytes).",
                status_code=502
            )

        if len(raw_bytes) < 32:
            raise ImageGenerationError("Pollinations returned an empty or truncated response.", status_code=502)

        # 3. Image Magic / MIME validation
        fmt, parsed_w, parsed_h = detect_image_format_and_dimensions(raw_bytes)
        if fmt == "unknown":
            preview = raw_bytes[:200].decode("utf-8", errors="replace")
            logger.error(f"Pollinations returned invalid non-image payload: {preview}")
            raise ImageGenerationError("Pollinations returned an invalid non-image response.", status_code=502)

        actual_w = parsed_w or width
        actual_h = parsed_h or height

        logger.info(
            f"Pollinations generated valid {fmt.upper()} image successfully "
            f"({len(raw_bytes)} bytes, {actual_w}x{actual_h}) in {elapsed_ms}ms."
        )

        metadata_dict = {
            "revised_prompt": clean_prompt,
            "generation_time_ms": elapsed_ms,
            "format": fmt,
            "simulated": False,
            "width": actual_w,
            "height": actual_h,
            "provider": self.provider_name,
            "model": self.model_name
        }

        return raw_bytes, metadata_dict
