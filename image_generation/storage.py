"""
Safe disk storage manager for TONY AI Image Generation (Stage 6).
Generates collision-free filenames, writes files safely, and enforces path sandboxing.
"""
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, List
from image_generation.safety import validate_safe_filename, validate_safe_output_path


class ImageStorage:
    """Manages physical storage of generated image files on the local filesystem."""

    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def generate_image_identifiers(self, prefix: str = "tony_img", ext: str = "png") -> Tuple[str, str]:
        """
        Generate a unique image ID and filename.
        Example:
            image_id = 'img_20261004_123456_a1b2c3'
            filename = 'tony_img_20261004_123456_a1b2c3.png'
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        token = uuid.uuid4().hex[:6]
        image_id = f"img_{timestamp}_{token}"
        clean_ext = ext.lstrip(".").lower()
        if clean_ext not in ("png", "jpg", "jpeg", "webp"):
            clean_ext = "png"
        filename = f"{prefix}_{timestamp}_{token}.{clean_ext}"
        return image_id, filename

    def save_image_bytes(
        self,
        image_bytes: bytes,
        image_id: Optional[str] = None,
        filename: Optional[str] = None,
        ext: Optional[str] = None
    ) -> Tuple[str, str, Path, int]:
        """
        Write image bytes to disk safely.

        :param image_bytes: Raw image bytes to store.
        :param image_id: Optional explicit image ID.
        :param filename: Optional explicit filename.
        :param ext: Optional format extension ('png', 'jpg', 'jpeg', 'webp').
        :return: Tuple of (image_id, filename, file_path, file_size_bytes)
        """
        if not image_id or not filename:
            # Auto-detect extension from magic bytes if not explicitly provided
            if not ext:
                if image_bytes.startswith(b"\xff\xd8\xff"):
                    ext = "jpg"
                elif image_bytes.startswith(b"RIFF") and len(image_bytes) >= 12 and image_bytes[8:12] == b"WEBP":
                    ext = "webp"
                else:
                    ext = "png"

            generated_id, generated_filename = self.generate_image_identifiers(ext=ext)
            image_id = image_id or generated_id
            filename = filename or generated_filename

        validate_safe_filename(filename, allowed_extensions=("png", "jpg", "jpeg", "webp"))
        target_path = self.storage_dir / filename
        safe_path = validate_safe_output_path(target_path, self.storage_dir)

        # Write image bytes to file
        safe_path.write_bytes(image_bytes)
        file_size = safe_path.stat().st_size

        return image_id, filename, safe_path, file_size

    def get_image_path(self, filename: str) -> Optional[Path]:
        """
        Locate and validate image file path within the storage sandbox.
        """
        try:
            validate_safe_filename(filename, allowed_extensions=("png", "jpg", "jpeg", "webp"))
            target = self.storage_dir / filename
            safe_path = validate_safe_output_path(target, self.storage_dir)
            if safe_path.is_file():
                return safe_path
            return None
        except Exception:
            return None

    def delete_image_file(self, filename: str) -> bool:
        """
        Delete an image file from storage safely.
        """
        path = self.get_image_path(filename)
        if path and path.is_file():
            try:
                path.unlink()
                return True
            except OSError:
                return False
        return False

    def list_files(self) -> List[Path]:
        """List all PNG files in storage sorted by modification time (newest first)."""
        files = list(self.storage_dir.glob("*.png"))
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files
