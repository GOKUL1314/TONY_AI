"""
Exceptions and error hierarchy for TONY AI Image Generation subsystem (Stage 6).
"""


class ImageGenerationError(Exception):
    """Base exception for all image generation errors."""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ProviderUnavailableError(ImageGenerationError):
    """Raised when the configured image provider is unreachable or lacks credentials."""
    def __init__(self, message: str = "Image generation provider is currently unavailable.", status_code: int = 503):
        super().__init__(message, status_code=status_code)


class SafetyViolationError(ImageGenerationError):
    """Raised when a prompt violates safety policies or contains forbidden/sensitive terms."""
    def __init__(self, message: str = "The requested image prompt violates safety policies."):
        super().__init__(message, status_code=400)


class RateLimitExceededError(ImageGenerationError):
    """Raised when provider rate limits or quotas are exceeded."""
    def __init__(self, message: str = "Image generation rate limit exceeded. Please try again shortly."):
        super().__init__(message, status_code=429)


class InvalidPromptError(ImageGenerationError):
    """Raised when an image prompt is empty, unparseable, or invalid."""
    def __init__(self, message: str = "A valid, non-empty image prompt is required."):
        super().__init__(message, status_code=400)


class ImageNotFoundError(ImageGenerationError):
    """Raised when an image ID cannot be found in storage or history."""
    def __init__(self, message: str = "Requested image could not be found."):
        super().__init__(message, status_code=404)
