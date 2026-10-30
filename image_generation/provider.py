"""
Image Provider Factory for TONY AI (Stage 6).
Instantiates and configures the appropriate image generation provider.
"""
import logging
from typing import Any
from image_generation.base import BaseImageProvider
from image_generation.mock_provider import MockImageProvider
from image_generation.cloud_provider import OpenAIImageProvider
from image_generation.pollinations_provider import PollinationsImageProvider

logger = logging.getLogger("tony.image_generation.provider")


def get_image_provider(config: Any) -> BaseImageProvider:
    """
    Factory function to instantiate the configured image provider.

    :param config: Application configuration object or dict.
    :return: Concrete implementation of BaseImageProvider.
    """
    provider_type = getattr(config, "IMAGE_PROVIDER", "pollinations").lower().strip()
    model_name = getattr(config, "IMAGE_MODEL", "").strip()

    logger.info(f"Initializing Image Provider: '{provider_type}' [Model: '{model_name}']")

    if provider_type in ("pollinations", "sana", "flux", "free"):
        base_url = getattr(config, "POLLINATIONS_API_BASE_URL", "https://image.pollinations.ai")
        timeout = getattr(config, "IMAGE_TIMEOUT", 60)
        return PollinationsImageProvider(
            model_name=model_name or "sana",
            base_url=base_url,
            timeout=timeout
        )

    if provider_type in ("openai", "dall-e", "cloud"):
        api_key = getattr(config, "IMAGE_API_KEY", "")
        base_url = getattr(config, "IMAGE_API_BASE_URL", "https://api.openai.com/v1")
        timeout = getattr(config, "IMAGE_TIMEOUT", 60)
        return OpenAIImageProvider(
            api_key=api_key,
            model_name=model_name or "dall-e-3",
            base_url=base_url,
            timeout=timeout
        )

    # Default / fallback: deterministic offline mock provider
    if provider_type not in ("mock", "local"):
        logger.warning(f"Unrecognized IMAGE_PROVIDER '{provider_type}'. Falling back to 'mock' provider.")

    return MockImageProvider(model_name=model_name or "mock-image-v1")
