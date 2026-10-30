"""
AI Provider abstraction layer for TONY.
Defines the base interface that all inference providers must implement.
"""
from abc import ABC, abstractmethod
import logging
from typing import Any

logger = logging.getLogger("tony.ai")


class AIProviderError(Exception):
    """Base exception for AI provider operations."""
    pass


class AIProvider(ABC):
    """
    Abstract Base Class for AI model providers.
    Enables swapping between local inference (Ollama), cloud APIs, or mock modes.
    """

    def __init__(self, model_name: str):
        self.model_name = model_name

    @abstractmethod
    def generate_response(self, message: str, history: list[dict[str, str]] | None = None) -> str:
        """
        Generate a text response given the current user message and conversation history.

        :param message: The latest user prompt.
        :param history: List of conversation turn dicts: [{'role': 'user'|'assistant', 'message': '...'}]
        :return: Generated response string.
        """
        pass

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        """
        Check connectivity and health of the provider engine.

        :return: Dict containing availability status and details.
        """
        pass


def get_ai_provider(config) -> AIProvider:
    """
    Factory function to instantiate the configured AI provider.

    :param config: The application Config object or class.
    :return: An instance of AIProvider.
    """
    provider_type = config.AI_PROVIDER.lower().strip()
    logger.info(f"Initializing AI Provider: '{provider_type}' with model: '{config.AI_MODEL}'")

    if provider_type == "local":
        from ai.local_provider import LocalProvider
        return LocalProvider(
            model_name=config.AI_MODEL,
            base_url=config.OLLAMA_BASE_URL,
            timeout=config.OLLAMA_TIMEOUT,
            system_prompt=config.SYSTEM_PROMPT,
        )
    elif provider_type == "api":
        from ai.api_provider import APIProvider
        return APIProvider(
            model_name=config.AI_MODEL,
            api_key=config.API_KEY,
            base_url=config.API_BASE_URL,
            timeout=config.API_TIMEOUT,
            system_prompt=config.SYSTEM_PROMPT,
        )
    elif provider_type == "mock":
        from ai.mock_provider import MockProvider
        return MockProvider(
            model_name=config.AI_MODEL,
            system_prompt=config.SYSTEM_PROMPT,
        )
    else:
        raise ValueError(
            f"Unsupported AI_PROVIDER '{provider_type}'. "
            f"Supported providers: 'local', 'api', 'mock'."
        )
