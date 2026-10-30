"""
Secure Storage Manager for TONY AI Vision Subsystem (Stage 9).
Handles upload validation, magic byte inspection, path sandboxing, and collision-free storage.
"""
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, List

from vision.errors import (
    UnsupportedFormatError,
    ImageSizeExceededError,
    ImageValidationError,
    ImageNotFoundError
)

# Magic bytes for strict format validation
MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
MAGIC_JPEG = b"\xff\xd8\xff"
MAGIC_RIFF = b"RIFF"
MAGIC_WEBP = b"WEBP"

ALLOWED_EXTENSIONS = ("png", "jpg", "jpeg", "webp")


def detect_image_format_from_bytes(data: bytes) -> str:
    """
    Inspect magic bytes to determine the actual image format.
    Raises ImageValidationError or UnsupportedFormatError if invalid.
    """
    if not data or len(data) < 12:
        raise ImageValidationError("File is empty or too small to be a valid image.")

    if data.startswith(MAGIC_PNG):
        return "png"
    elif data.startswith(MAGIC_JPEG):
        return "jpg"
    elif data.startswith(MAGIC_RIFF) and data[8:12] == MAGIC_WEBP:
        return "webp"
    else:
        raise UnsupportedFormatError(
            "Unsupported file format. Only valid PNG, JPEG, and WebP images are permitted."
        )


def sanitize_filename(filename: str) -> str:
    """
    Sanitize an uploaded filename to prevent directory traversal and illegal characters.
    """
    if not filename:
        return "uploaded_image.png"

    # Strip null bytes and control chars
    clean = filename.replace("\x00", "")
    # Remove directory paths
    clean = os.path.basename(clean)
    # Remove unsafe characters
    clean = re.sub(r'[^\w\.-]', '_', clean)
    # Prevent leading dots
    clean = clean.lstrip(".")
    if not clean:
        clean = "uploaded_image.png"
    return clean


class VisionStorage:
    """Manages physical disk storage of uploaded visual analysis images."""

    def __init__(self, storage_dir: Path, max_size_mb: int = 10):
        self.storage_dir = Path(storage_dir).resolve()
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def validate_safe_path(self, target_path: Path) -> Path:
        """Enforce path sandboxing within the storage directory."""
        resolved = Path(target_path).resolve()
        try:
            resolved.relative_to(self.storage_dir)
        except ValueError:
            raise ImageValidationError(f"Path traversal detected: {target_path} is outside {self.storage_dir}")
        return resolved

    def generate_identifiers(self, ext: str = "png") -> Tuple[str, str]:
        """Generate unique image ID and filename."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        token = uuid.uuid4().hex[:6]
        image_id = f"vis_{ts}_{token}"
        clean_ext = ext.lstrip(".").lower()
        if clean_ext not in ALLOWED_EXTENSIONS:
            clean_ext = "png"
        filename = f"tony_vision_{ts}_{token}.{clean_ext}"
        return image_id, filename

    def save_upload(
        self,
        image_bytes: bytes,
        original_filename: Optional[str] = None
    ) -> Tuple[str, str, Path, int]:
        """
        Validate and save uploaded image bytes.

        :param image_bytes: Raw bytes of the uploaded file.
        :param original_filename: Original client filename for format hinting.
        :return: Tuple of (image_id, filename, file_path, file_size)
        :raises ImageSizeExceededError: If file exceeds maximum allowed size.
        :raises UnsupportedFormatError: If magic bytes do not match PNG/JPEG/WebP.
        :raises ImageValidationError: If corrupted or path violation.
        """
        file_size = len(image_bytes)
        if file_size > self.max_size_bytes:
            raise ImageSizeExceededError(
                f"File size ({file_size} bytes) exceeds maximum limit of {self.max_size_bytes} bytes ({self.max_size_bytes // (1024*1024)}MB)."
            )

        # 1. Magic byte format detection
        detected_ext = detect_image_format_from_bytes(image_bytes)

        # 2. Check original filename extension if provided
        if original_filename:
            sanitized = sanitize_filename(original_filename)
            ext = sanitized.split(".")[-1].lower() if "." in sanitized else ""
            if ext and ext not in ALLOWED_EXTENSIONS:
                raise UnsupportedFormatError(
                    f"Invalid extension '{ext}'. Only PNG, JPEG, and WebP are allowed."
                )
            if ext and ext in ("jpg", "jpeg") and detected_ext != "jpg":
                raise ImageValidationError("File extension does not match true binary content (magic bytes).")
            if ext and ext == "png" and detected_ext != "png":
                raise ImageValidationError("File extension does not match true binary content (magic bytes).")
            if ext and ext == "webp" and detected_ext != "webp":
                raise ImageValidationError("File extension does not match true binary content (magic bytes).")

        # 3. Create unique collision-free file in sandboxed directory
        image_id, filename = self.generate_identifiers(ext=detected_ext)
        target_path = self.storage_dir / filename
        safe_path = self.validate_safe_path(target_path)

        # 4. Write bytes to disk
        safe_path.write_bytes(image_bytes)
        return image_id, filename, safe_path, file_size

    def get_image_path(self, image_id: str) -> Optional[Path]:
        """Look up image file on disk by image_id or filename."""
        clean_id = sanitize_filename(image_id)
        # Search direct file or files matching ID prefix
        for path in self.storage_dir.iterdir():
            if path.is_file() and (clean_id in path.name or path.stem == clean_id):
                return self.validate_safe_path(path)
        return None

    def get_image_bytes(self, image_id: str) -> bytes:
        """Retrieve raw image bytes for an image ID."""
        path = self.get_image_path(image_id)
        if not path or not path.is_file():
            raise ImageNotFoundError(f"Image '{image_id}' not found in vision storage.")
        return path.read_bytes()

    def list_images(self) -> List[Path]:
        """List all stored uploaded images sorted by modification time."""
        files = [p for p in self.storage_dir.iterdir() if p.is_file()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files
