"""
Exception hierarchy for TONY AI Video Generation subsystem (Stage 7).
Provides structured, safe exception types without leaking credentials or internal paths.
"""
from typing import Optional


class VideoGenerationError(Exception):
    """Base exception for all video generation failures."""
    def __init__(self, message: str, code: str = "VIDEO_GENERATION_ERROR", status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class VideoAuthenticationError(VideoGenerationError):
    """Raised when provider authentication fails or credentials lack permissions."""
    def __init__(self, message: str = "Hugging Face authentication failed. Please verify your HF_TOKEN."):
        super().__init__(message, code="AUTHENTICATION_FAILED", status_code=401)


class ProviderUnavailableError(VideoGenerationError):
    """Raised when the selected video provider backend is offline, unconfigured, or unreachable."""
    def __init__(self, message: str = "Video provider is unavailable."):
        super().__init__(message, code="PROVIDER_UNAVAILABLE", status_code=503)


class FreeQuotaUnavailableError(VideoGenerationError):
    """
    Raised when free Hugging Face inference quota is exhausted or serverless free tier is unavailable.
    Provides structured code VIDEO_FREE_QUOTA_UNAVAILABLE.
    """
    def __init__(self, message: str = "Free video generation is currently unavailable. You can configure a local video model or explicitly enable a paid provider."):
        super().__init__(message, code="VIDEO_FREE_QUOTA_UNAVAILABLE", status_code=402)


class LocalVideoUnavailableError(VideoGenerationError):
    """Raised when local video generation cannot run due to missing weights or insufficient hardware."""
    def __init__(self, message: str = "Local video generation is not configured or your computer does not meet the hardware requirements."):
        super().__init__(message, code="LOCAL_VIDEO_UNAVAILABLE", status_code=503)


class PaidProviderBlockedError(VideoGenerationError):
    """Raised when paid video generation is attempted while VIDEO_ALLOW_PAID is false."""
    def __init__(self, message: str = "Paid video generation is disabled in TONY's Free-Safe Mode."):
        super().__init__(message, code="PAID_PROVIDER_BLOCKED", status_code=403)


class VideoTimeoutError(VideoGenerationError):
    """Raised when video generation exceeds the allocated time limit."""
    def __init__(self, message: str = "Video generation timed out."):
        super().__init__(message, code="VIDEO_TIMEOUT", status_code=504)


class VideoCancelledError(VideoGenerationError):
    """Raised when video generation is cancelled by the operator."""
    def __init__(self, message: str = "Video generation was cancelled."):
        super().__init__(message, code="VIDEO_CANCELLED", status_code=499)


class UnsupportedVideoCapabilityError(VideoGenerationError):
    """Raised when a requested feature (e.g. image-to-video) is unsupported by the active provider/model."""
    def __init__(self, message: str = "The selected video model does not support this capability."):
        super().__init__(message, code="UNSUPPORTED_CAPABILITY", status_code=400)


class VideoValidationError(VideoGenerationError):
    """Raised when request parameters fail validation (e.g. duration > max allowed, invalid dimensions)."""
    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR", status_code=400)


class SafetyViolationError(VideoGenerationError):
    """Raised when a prompt or input violates content safety or contains sensitive credentials."""
    def __init__(self, message: str):
        super().__init__(message, code="SAFETY_VIOLATION", status_code=400)


class VideoNotFoundError(VideoGenerationError):
    """Raised when a requested video asset or job ID does not exist."""
    def __init__(self, message: str = "Video not found."):
        super().__init__(message, code="VIDEO_NOT_FOUND", status_code=404)


class VideoStorageError(VideoGenerationError):
    """Raised when local filesystem operations fail for video or thumbnail assets."""
    def __init__(self, message: str = "Video storage error."):
        super().__init__(message, code="STORAGE_ERROR", status_code=500)
