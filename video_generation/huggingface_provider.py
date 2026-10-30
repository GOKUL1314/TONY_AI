"""
Hugging Face Video Generation Provider for TONY AI (Stage 7).
Uses official huggingface_hub InferenceClient with strict free-mode cost protection,
token masking, and seamless error handling for serverless inference.
"""
import time
import logging
from typing import Tuple, Dict, Any, Optional, Callable
from video_generation.base import VideoProvider
from video_generation.models import VideoGenerationRequest
from video_generation.safety import mask_secret
from video_generation.errors import (
    VideoGenerationError,
    VideoAuthenticationError,
    ProviderUnavailableError,
    FreeQuotaUnavailableError,
    PaidProviderBlockedError,
    UnsupportedVideoCapabilityError,
    VideoTimeoutError
)

logger = logging.getLogger("tony.video_generation.huggingface")


class HuggingFaceVideoProvider(VideoProvider):
    """
    Video generation backend utilizing Hugging Face Serverless / Inference Providers.
    Strictly observes free-tier allowances and prevents accidental paid charges.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        model_name: str = "Wan-AI/Wan2.1-T2V-14B",
        provider: Optional[str] = "wavespeed",
        allow_paid: bool = False,
        timeout: int = 300
    ):
        super().__init__(
            provider_name="huggingface",
            model_name=model_name or "Wan-AI/Wan2.1-T2V-14B",
            supports_text_to_video=True,
            supports_image_to_video=True,
            supports_cancellation=False
        )
        self.token = token.strip() if token else None
        self.hf_provider = provider.strip() if provider else "wavespeed"
        self.allow_paid = allow_paid
        self.timeout = timeout
        self._client = None

    def _sanitize_error(self, err_msg: str) -> str:
        """Strip any token occurrences from an error message string."""
        if not err_msg:
            return ""
        sanitized = err_msg
        if self.token:
            sanitized = sanitized.replace(self.token, "[REDACTED_HF_TOKEN]")
        return sanitized

    def _get_client(self):
        """Lazy-initialize huggingface_hub InferenceClient."""
        if self._client is not None:
            return self._client

        if not self.token:
            raise ProviderUnavailableError("Hugging Face is selected, but no HF token is configured.")

        try:
            from huggingface_hub import InferenceClient
            # If a custom inference provider is configured (e.g. fal-ai, replicate)
            kwargs: Dict[str, Any] = {
                "token": self.token,
                "timeout": self.timeout
            }
            if self.hf_provider:
                kwargs["provider"] = self.hf_provider

            self._client = InferenceClient(**kwargs)
            return self._client
        except Exception as e:
            sanitized_err = self._sanitize_error(str(e))
            logger.error(f"Failed to instantiate Hugging Face InferenceClient: {sanitized_err}")
            raise ProviderUnavailableError(f"Hugging Face initialization error: {sanitized_err}")

    def _execute_task_inference(
        self,
        client: Any,
        task: str,
        inputs: Any,
        parameters: Dict[str, Any],
        progress_callback: Optional[Callable[[Optional[int], str], None]] = None
    ) -> bytes:
        """
        Execute text-to-video or image-to-video inference.
        Wraps official huggingface_hub client and handles asynchronous FalAI queue lifecycle
        with safe status polling, result retrieval, and proper error handling.
        """
        # If client is a mock or not a real InferenceClient, call standard client methods directly
        try:
            from huggingface_hub import InferenceClient
            from huggingface_hub.inference._providers import get_provider_helper
            from huggingface_hub.inference._providers.fal_ai import FalAIQueueTask
            provider_helper = get_provider_helper(self.hf_provider, task=task, model=self.model_name)
        except Exception:
            provider_helper = None

        if not isinstance(client, InferenceClient) or not isinstance(provider_helper, FalAIQueueTask):
            if task == "text-to-video":
                return client.text_to_video(prompt=inputs, **parameters)
            else:
                return client.image_to_video(image=inputs, **parameters)

        # Provider uses FalAIQueueTask (e.g. fal-ai routing for Wan-AI models)
        import json
        from urllib.parse import urlparse
        from huggingface_hub.utils import get_session, hf_raise_for_status

        request_parameters = provider_helper.prepare_request(
            inputs=inputs,
            parameters=parameters,
            headers=client.headers,
            model=self.model_name,
            api_key=client.token,
        )

        raw_resp = client._inner_post(request_parameters)
        response_dict = json.loads(raw_resp) if isinstance(raw_resp, (str, bytes)) else raw_resp

        request_id = response_dict.get("request_id")
        if not request_id:
            # If not queued, maybe direct response
            if isinstance(response_dict, dict) and "video" in response_dict:
                return get_session().get(response_dict["video"]["url"]).content
            raise VideoGenerationError(f"Unexpected initial response from {self.hf_provider or 'huggingface'}: {response_dict}")

        response_url = response_dict.get("response_url")
        parsed_url = urlparse(request_parameters.url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{'/fal-ai' if parsed_url.netloc == 'router.huggingface.co' else ''}"
        query_param = f"?{parsed_url.query}" if parsed_url.query else ""
        model_path = urlparse(response_url).path if response_url else ""
        status_url = f"{base_url}{str(model_path)}/status{query_param}"
        result_url = f"{base_url}{str(model_path)}{query_param}"

        status = response_dict.get("status")
        session = get_session()
        last_status_data = response_dict
        poll_interval = 2.0
        max_polls = max(int(self.timeout / poll_interval), 10)
        polls = 0

        while status not in ("COMPLETED", "FAILED", "ERROR") and polls < max_polls:
            time.sleep(poll_interval)
            polls += 1
            if progress_callback:
                progress_callback(None, f"Generating video on Hugging Face (status: {status})...")
            status_resp = session.get(status_url, headers=request_parameters.headers, timeout=self.timeout)
            hf_raise_for_status(status_resp)
            last_status_data = status_resp.json()
            status = last_status_data.get("status")

        if status not in ("COMPLETED", "FAILED", "ERROR"):
            raise VideoTimeoutError(f"Hugging Face video generation timed out after {self.timeout}s.")

        if status in ("FAILED", "ERROR"):
            err_msg = last_status_data.get("error") or "Generation job failed upstream."
            raise ProviderUnavailableError(f"Hugging Face video generation failed upstream: {err_msg}")

        # Check if video URL is already present in status data
        video_url = None
        if "video" in last_status_data and isinstance(last_status_data["video"], dict):
            video_url = last_status_data["video"].get("url")
        elif "payload" in last_status_data and isinstance(last_status_data["payload"], dict):
            video_url = last_status_data["payload"].get("video", {}).get("url")
        elif "output" in last_status_data and isinstance(last_status_data["output"], dict):
            video_url = last_status_data["output"].get("video", {}).get("url")

        # If not embedded, fetch result from result_url
        if not video_url:
            res_resp = session.get(result_url, headers=request_parameters.headers, timeout=self.timeout)
            if res_resp.status_code == 200:
                res_data = res_resp.json()
                if isinstance(res_data, dict):
                    if "video" in res_data and isinstance(res_data["video"], dict):
                        video_url = res_data["video"].get("url")
                    elif "payload" in res_data and isinstance(res_data["payload"], dict):
                        video_url = res_data["payload"].get("video", {}).get("url")
            else:
                try:
                    detail = res_resp.json().get("detail") or res_resp.text
                except Exception:
                    detail = res_resp.text
                raise ProviderUnavailableError(
                    f"Hugging Face serverless provider for '{self.model_name}' did not return a video payload. "
                    f"Result retrieval returned HTTP {res_resp.status_code} ({detail}). The model endpoint is currently unavailable on Hugging Face Inference Providers."
                )

        if not video_url:
            raise ProviderUnavailableError(
                f"Hugging Face serverless provider for '{self.model_name}' did not return a video URL in the completed result."
            )

        if progress_callback:
            progress_callback(None, "Downloading generated video from Hugging Face...")
        media_resp = session.get(video_url, timeout=self.timeout)
        hf_raise_for_status(media_resp)
        return media_resp.content

    def generate_text_to_video(
        self,
        request: VideoGenerationRequest,
        progress_callback: Optional[Callable[[Optional[int], str], None]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate video from prompt using Hugging Face text-to-video inference.
        """
        if not self.token:
            raise ProviderUnavailableError("Hugging Face is selected, but no HF token is configured.")

        t0 = time.time()
        client = self._get_client()

        if progress_callback:
            progress_callback(None, "Connecting to Hugging Face Inference API...")

        logger.info(
            f"Dispatching text-to-video to Hugging Face [Model: {self.model_name}] "
            f"(Token: {'PRESENT' if self.token else 'NOT CONFIGURED'}, Provider: {self.hf_provider or 'default'}, PaidAllowed: {self.allow_paid})"
        )

        try:
            if progress_callback:
                progress_callback(None, "Processing video generation on Hugging Face (uses available free allowance)...")

            # Call official huggingface_hub text_to_video
            call_kwargs: Dict[str, Any] = {
                "model": self.model_name
            }
            # Add optional duration / frames if applicable
            if request.duration and request.fps:
                call_kwargs["num_frames"] = min(int(request.duration * request.fps), 80)
            if request.seed is not None:
                call_kwargs["seed"] = request.seed
            if request.negative_prompt:
                call_kwargs["negative_prompt"] = [request.negative_prompt]

            video_bytes = self._execute_task_inference(
                client=client,
                task="text-to-video",
                inputs=request.prompt,
                parameters=call_kwargs,
                progress_callback=progress_callback
            )

            if not video_bytes or len(video_bytes) == 0:
                raise VideoGenerationError("Hugging Face returned empty video payload.")

            elapsed_ms = int((time.time() - t0) * 1000)
            metadata = {
                "provider": self.provider_name,
                "model": self.model_name,
                "hf_provider": self.hf_provider or "default",
                "simulated": False,
                "generation_time_ms": elapsed_ms,
                "prompt": request.prompt,
                "width": request.width,
                "height": request.height,
                "duration": request.duration,
                "fps": request.fps,
                "format": "mp4"
            }
            return video_bytes, metadata

        except Exception as e:
            raw_err = str(e)
            sanitized_err = self._sanitize_error(raw_err)
            err_lower = sanitized_err.lower()

            logger.warning(f"Hugging Face text-to-video failed: {sanitized_err}")

            # 0. Authentication / Permission rejection
            if "401" in err_lower or "unauthorized" in err_lower or "invalid username or password" in err_lower:
                raise VideoAuthenticationError(
                    "Hugging Face authentication failed. Please verify your HF_TOKEN has valid permissions."
                )
            if "403" in err_lower or "forbidden" in err_lower:
                raise VideoAuthenticationError(
                    "Hugging Face access forbidden. Your HF_TOKEN may lack required permissions for this model or provider."
                )

            # 1. Payment / Billing / Paid Provider rejection
            if (
                "402" in err_lower
                or "payment" in err_lower
                or "billing" in err_lower
                or "quota" in err_lower
                or "credit" in err_lower
                or "balance" in err_lower
                or "insufficient" in err_lower
            ):
                if not self.allow_paid:
                    raise FreeQuotaUnavailableError(
                        "Your available free Hugging Face video inference is unavailable or exhausted."
                    )
                else:
                    raise VideoGenerationError(f"Hugging Face payment/quota error: {sanitized_err}")

            # 2. Rate limit / Serverless capacity exhausted
            if "429" in err_lower or "rate limit" in err_lower or "too many requests" in err_lower:
                raise FreeQuotaUnavailableError(
                    "Free Hugging Face video generation rate limit reached. Please try again shortly or configure a local model."
                )

            # 3. Timeout
            if "timeout" in err_lower or "timed out" in err_lower:
                raise VideoTimeoutError(f"Hugging Face generation timed out after {self.timeout}s.")

            # 4. Model capability mismatch
            if "not supported" in err_lower or "task not supported" in err_lower or "404" in err_lower:
                raise UnsupportedVideoCapabilityError(
                    f"Model '{self.model_name}' does not support text-to-video on the active provider endpoint."
                )

            # 5. Upstream provider response error (e.g. missing video payload or endpoint unavailable)
            if isinstance(e, KeyError) and "video" in err_lower:
                raise ProviderUnavailableError(
                    f"Hugging Face serverless provider for '{self.model_name}' did not return a video payload. The model endpoint is currently unavailable on Hugging Face Inference Providers."
                )

            raise VideoGenerationError(f"Hugging Face generation failed: {sanitized_err}")

    def generate_image_to_video(
        self,
        request: VideoGenerationRequest,
        image_bytes: bytes,
        progress_callback: Optional[Callable[[Optional[int], str], None]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Animate an image using Hugging Face image-to-video inference.
        """
        if not self.token:
            raise ProviderUnavailableError("Hugging Face is selected, but no HF token is configured.")

        t0 = time.time()
        client = self._get_client()

        if progress_callback:
            progress_callback(None, "Connecting to Hugging Face Image-to-Video endpoint...")

        logger.info(
            f"Dispatching image-to-video to Hugging Face [Model: {self.model_name}] "
            f"(Source size: {len(image_bytes)} bytes)"
        )

        try:
            if progress_callback:
                progress_callback(None, "Processing image animation on Hugging Face...")

            call_kwargs: Dict[str, Any] = {
                "model": self.model_name,
                "prompt": request.prompt
            }
            if request.seed is not None:
                call_kwargs["seed"] = request.seed

            video_bytes = self._execute_task_inference(
                client=client,
                task="image-to-video",
                inputs=image_bytes,
                parameters=call_kwargs,
                progress_callback=progress_callback
            )

            if not video_bytes or len(video_bytes) == 0:
                raise VideoGenerationError("Hugging Face returned empty video payload for image animation.")

            elapsed_ms = int((time.time() - t0) * 1000)
            metadata = {
                "provider": self.provider_name,
                "model": self.model_name,
                "hf_provider": self.hf_provider or "default",
                "simulated": False,
                "generation_time_ms": elapsed_ms,
                "prompt": request.prompt,
                "parent_image_id": request.parent_image_id,
                "width": request.width,
                "height": request.height,
                "duration": request.duration,
                "fps": request.fps,
                "format": "mp4"
            }
            return video_bytes, metadata

        except Exception as e:
            raw_err = str(e)
            sanitized_err = self._sanitize_error(raw_err)
            err_lower = sanitized_err.lower()

            logger.warning(f"Hugging Face image-to-video failed: {sanitized_err}")

            # 0. Authentication / Permission rejection
            if "401" in err_lower or "unauthorized" in err_lower or "invalid username or password" in err_lower:
                raise VideoAuthenticationError(
                    "Hugging Face authentication failed. Please verify your HF_TOKEN has valid permissions."
                )
            if "403" in err_lower or "forbidden" in err_lower:
                raise VideoAuthenticationError(
                    "Hugging Face access forbidden. Your HF_TOKEN may lack required permissions for this model or provider."
                )

            if (
                "402" in err_lower
                or "payment" in err_lower
                or "billing" in err_lower
                or "quota" in err_lower
                or "credit" in err_lower
                or "balance" in err_lower
                or "insufficient" in err_lower
            ):
                if not self.allow_paid:
                    raise FreeQuotaUnavailableError(
                        "Your available free Hugging Face video inference is unavailable or exhausted."
                    )
            if "429" in err_lower or "rate limit" in err_lower:
                raise FreeQuotaUnavailableError(
                    "Free Hugging Face video generation rate limit reached. Please try again shortly."
                )
            if "not supported" in err_lower or "task" in err_lower or "404" in err_lower:
                raise UnsupportedVideoCapabilityError(
                    f"Selected model '{self.model_name}' does not support image-to-video animation on this provider."
                )

            # Upstream provider response error
            if isinstance(e, KeyError) and "video" in err_lower:
                raise ProviderUnavailableError(
                    f"Hugging Face serverless provider for '{self.model_name}' did not return a video payload. The model endpoint is currently unavailable on Hugging Face Inference Providers."
                )

            raise VideoGenerationError(f"Hugging Face image animation failed: {sanitized_err}")

    def check_health(self) -> Dict[str, Any]:
        """Verify configuration and readiness of the Hugging Face provider."""
        has_token = bool(self.token)
        return {
            "available": has_token,
            "provider": self.provider_name,
            "model": self.model_name,
            "hf_provider": self.hf_provider or "default",
            "token_configured": has_token,
            "token_status": "PRESENT" if has_token else "NOT CONFIGURED",
            "free_mode_active": not self.allow_paid,
            "paid_fallback_enabled": self.allow_paid,
            "status": "ready" if has_token else "missing_token",
            "message": "Uses available free Hugging Face allowance." if has_token else "HF_TOKEN not configured."
        }
