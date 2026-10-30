"""
Provider Factory for TONY AI Vision Subsystem (Stage 9).
Dynamically instantiates vision providers based on configuration.
"""
import logging
from vision.base import BaseVisionProvider
from vision.mock_provider import MockVisionProvider
from vision.ollama_provider import OllamaVisionProvider
from vision.errors import VisionProviderError

logger = logging.getLogger("tony.vision.factory")


def get_vision_provider(config) -> BaseVisionProvider:
    """
    Instantiate and return the configured vision provider.

    :param config: Application configuration instance or dict.
    :return: Concrete BaseVisionProvider instance.
    :raises VisionProviderError: If the provider is unsupported or misconfigured.
    """
    provider_name = getattr(config, "VISION_PROVIDER", "ollama")
    if isinstance(provider_name, str):
        provider_name = provider_name.lower().strip()
    else:
        provider_name = "ollama"

    model_name = getattr(config, "VISION_MODEL", "moondream")
    if not model_name:
        model_name = "moondream"

    logger.info(f"Initializing Vision Provider: '{provider_name}' [Model: '{model_name}']")

    if provider_name == "mock":
        return MockVisionProvider(
            provider_name="mock",
            model_name=model_name
        )

    if provider_name in ("ollama", "local"):
        base_url = getattr(config, "OLLAMA_BASE_URL", "http://localhost:11434")
        timeout = getattr(config, "VISION_TIMEOUT", 90)
        return OllamaVisionProvider(
            model_name=model_name,
            base_url=base_url,
            timeout=timeout
        )

    raise VisionProviderError(
        f"Unknown or unsupported vision provider: '{provider_name}'. "
        "Valid options are: 'ollama', 'mock'."
    )
