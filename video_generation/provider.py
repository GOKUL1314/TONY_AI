"""
Provider factory and resolution for TONY AI Video Generation (Stage 7).
Enforces provider priority: LOCAL -> HUGGING FACE -> MOCK, and strictly respects
cost safety policies (never silently enabling paid generation).
"""
import logging
from typing import Any
from video_generation.base import VideoProvider
from video_generation.mock_provider import MockVideoProvider
from video_generation.huggingface_provider import HuggingFaceVideoProvider
from video_generation.local_provider import LocalVideoProvider, detect_local_hardware

logger = logging.getLogger("tony.video_generation.provider")


def create_video_provider(config: Any) -> VideoProvider:
    """
    Instantiate the configured video generation backend based on application settings.

    :param config: Application Config object.
    :return: Concrete VideoProvider instance.
    """
    provider_type = getattr(config, "VIDEO_PROVIDER", "huggingface").lower().strip()
    allow_paid = getattr(config, "VIDEO_ALLOW_PAID", False)
    hf_token = getattr(config, "HF_TOKEN", "")
    hf_model = getattr(config, "HF_VIDEO_MODEL", "Wan-AI/Wan2.1-T2V-14B")
    hf_provider = getattr(config, "HF_VIDEO_PROVIDER", "") or getattr(config, "HF_PROVIDER", "") or "wavespeed"
    timeout = getattr(config, "VIDEO_TIMEOUT", 300)

    local_model = getattr(config, "VIDEO_LOCAL_MODEL", "")
    local_path = getattr(config, "VIDEO_LOCAL_MODEL_PATH", "")
    local_device = getattr(config, "VIDEO_LOCAL_DEVICE", "auto")

    logger.info(
        f"Resolving Video Provider: '{provider_type}' (PaidAllowed: {allow_paid}, "
        f"HF_Model: '{hf_model}', LocalPath: '{local_path or 'none'}')"
    )

    if provider_type == "mock":
        logger.info("Initializing MockVideoProvider for testing.")
        return MockVideoProvider()

    elif provider_type == "local":
        logger.info("Initializing LocalVideoProvider.")
        return LocalVideoProvider(
            model_name=local_model or "local-diffusion-v1",
            model_path=local_path,
            device=local_device
        )

    elif provider_type == "huggingface":
        logger.info(f"Initializing HuggingFaceVideoProvider [Model: {hf_model}].")
        return HuggingFaceVideoProvider(
            token=hf_token,
            model_name=hf_model,
            provider=hf_provider if hf_provider else None,
            allow_paid=allow_paid,
            timeout=timeout
        )

    elif provider_type == "auto":
        # AUTO mode: Check LOCAL first, then HUGGING FACE, then MOCK
        logger.info("Auto provider mode selected: Checking local hardware capability...")
        local_report = detect_local_hardware(local_path)
        if local_report.provider_available:
            logger.info("Auto mode: Local video provider is ready and selected.")
            return LocalVideoProvider(
                model_name=local_model or "local-diffusion-v1",
                model_path=local_path,
                device=local_device
            )

        if hf_token:
            logger.info("Auto mode: Hugging Face token is configured. Selecting HuggingFaceVideoProvider.")
            return HuggingFaceVideoProvider(
                token=hf_token,
                model_name=hf_model,
                provider=hf_provider if hf_provider else None,
                allow_paid=allow_paid,
                timeout=timeout
            )

        logger.warning("Auto mode: Neither local hardware nor Hugging Face token available. Falling back to MockVideoProvider.")
        return MockVideoProvider()

    else:
        logger.warning(f"Unrecognized VIDEO_PROVIDER '{provider_type}'. Defaulting to MockVideoProvider.")
        return MockVideoProvider()


def get_video_provider(config: Any) -> VideoProvider:
    """Convenience alias for provider creation."""
    return create_video_provider(config)
