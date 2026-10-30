"""
Custom Exception Classes for TONY AI Vision Subsystem (Stage 9).
"""


class VisionError(Exception):
    """Base exception for all vision-related operations."""
    pass


class UnsupportedFormatError(VisionError):
    """Raised when an uploaded file is not an allowed image format (PNG, JPEG, WebP)."""
    pass


class ImageSizeExceededError(VisionError):
    """Raised when an uploaded image exceeds the maximum configured size limit."""
    pass


class ImageValidationError(VisionError):
    """Raised when image magic bytes or file structure validation fails."""
    pass


class VisionProviderError(VisionError):
    """Raised when an external or local vision inference backend fails."""
    pass


class VisionTimeoutError(VisionProviderError):
    """Raised when vision inference exceeds the configured timeout threshold."""
    pass


class ImageNotFoundError(VisionError):
    """Raised when an image ID or file path cannot be resolved."""
    pass
