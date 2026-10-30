"""
Safe disk storage manager for TONY AI Video Generation (Stage 7).
Handles collision-free filenames, video file persistence, thumbnail extraction via PyAV,
and strict filesystem sandboxing.
"""
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, List
import av
from video_generation.safety import validate_safe_filename, validate_safe_output_path
from video_generation.errors import VideoStorageError

logger = logging.getLogger("tony.video_generation.storage")


class VideoStorage:
    """Manages physical storage of generated videos and thumbnails on the local filesystem."""

    def __init__(self, storage_dir: Path, thumbnails_dir: Optional[Path] = None):
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        if thumbnails_dir:
            self.thumbnails_dir = Path(thumbnails_dir).resolve()
        else:
            self.thumbnails_dir = (self.storage_dir / "thumbnails").resolve()
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)

    def generate_video_identifiers(self, prefix: str = "video") -> Tuple[str, str, str]:
        """
        Generate unique identifiers for video ID, video filename, and thumbnail filename.
        Example:
            video_id = 'vid_20261004_123456_a1b2c3'
            video_filename = 'video_20261004_123456_a1b2c3.mp4'
            thumb_filename = 'video_20261004_123456_a1b2c3.jpg'
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        token = uuid.uuid4().hex[:6]
        video_id = f"vid_{timestamp}_{token}"
        video_filename = f"{prefix}_{timestamp}_{token}.mp4"
        thumb_filename = f"{prefix}_{timestamp}_{token}.jpg"
        return video_id, video_filename, thumb_filename

    def extract_thumbnail_from_video(self, video_path: Path, thumb_path: Path) -> bool:
        """
        Extract the first frame of an MP4 video file and write as JPEG using PyAV.
        """
        try:
            container = av.open(str(video_path))
            stream = container.streams.video[0]
            for frame in container.decode(stream):
                # We have the first frame
                out_container = av.open(str(thumb_path), mode="w", format="mjpeg")
                out_stream = out_container.add_stream("mjpeg", rate=1)
                out_stream.width = frame.width
                out_stream.height = frame.height
                out_stream.pix_fmt = "yuvj420p"

                for packet in out_stream.encode(frame):
                    out_container.mux(packet)
                for packet in out_stream.encode():
                    out_container.mux(packet)

                out_container.close()
                container.close()
                return True

            container.close()
            return False
        except Exception as e:
            logger.warning(f"Could not extract thumbnail from video '{video_path.name}': {e}")
            return False

    def save_video_bytes(
        self,
        video_bytes: bytes,
        video_id: Optional[str] = None,
        filename: Optional[str] = None
    ) -> Tuple[str, str, Path, int, Optional[str], Optional[Path]]:
        """
        Write video bytes to disk safely, and extract thumbnail if practical.

        :param video_bytes: Raw MP4/WebM bytes.
        :param video_id: Optional explicit video ID.
        :param filename: Optional explicit video filename.
        :return: Tuple of (video_id, filename, file_path, file_size_bytes, thumb_filename, thumb_path)
        """
        if not video_bytes or len(video_bytes) == 0:
            raise VideoStorageError("Cannot save empty video bytes (0 bytes).")

        gen_id, gen_vname, gen_tname = self.generate_video_identifiers()
        video_id = video_id or gen_id
        filename = filename or gen_vname
        thumb_filename = filename.rsplit(".", 1)[0] + ".jpg"

        validate_safe_filename(filename, allowed_extensions=(".mp4", ".webm"))
        validate_safe_filename(thumb_filename, allowed_extensions=(".jpg", ".png"))

        target_video_path = self.storage_dir / filename
        safe_video_path = validate_safe_output_path(target_video_path, self.storage_dir)

        # Write video file
        try:
            safe_video_path.write_bytes(video_bytes)
            file_size = safe_video_path.stat().st_size
        except OSError as e:
            raise VideoStorageError(f"Failed to write video file to disk: {e}")

        # Attempt thumbnail extraction
        target_thumb_path = self.thumbnails_dir / thumb_filename
        safe_thumb_path = validate_safe_output_path(target_thumb_path, self.thumbnails_dir)
        thumb_created = self.extract_thumbnail_from_video(safe_video_path, safe_thumb_path)

        actual_thumb_filename = thumb_filename if thumb_created else None
        actual_thumb_path = safe_thumb_path if thumb_created else None

        return video_id, filename, safe_video_path, file_size, actual_thumb_filename, actual_thumb_path

    def get_video_path(self, filename: str) -> Optional[Path]:
        """Locate and validate video file path within sandbox."""
        try:
            validate_safe_filename(filename, allowed_extensions=(".mp4", ".webm"))
            target = self.storage_dir / filename
            safe_path = validate_safe_output_path(target, self.storage_dir)
            if safe_path.is_file():
                return safe_path
            return None
        except Exception:
            return None

    def get_thumbnail_path(self, filename: str) -> Optional[Path]:
        """Locate and validate thumbnail file path within sandbox."""
        try:
            validate_safe_filename(filename, allowed_extensions=(".jpg", ".png"))
            target = self.thumbnails_dir / filename
            safe_path = validate_safe_output_path(target, self.thumbnails_dir)
            if safe_path.is_file():
                return safe_path
            return None
        except Exception:
            return None

    def delete_video_file(self, filename: str, thumb_filename: Optional[str] = None) -> bool:
        """Safely delete a video file and its associated thumbnail."""
        deleted = False
        vpath = self.get_video_path(filename)
        if vpath and vpath.is_file():
            try:
                vpath.unlink()
                deleted = True
            except OSError:
                pass

        if thumb_filename:
            tpath = self.get_thumbnail_path(thumb_filename)
            if tpath and tpath.is_file():
                try:
                    tpath.unlink()
                except OSError:
                    pass

        return deleted

    def list_files(self) -> List[Path]:
        """List all video files in storage sorted by modification time (newest first)."""
        files = [p for p in self.storage_dir.glob("*") if p.suffix.lower() in (".mp4", ".webm")]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files
