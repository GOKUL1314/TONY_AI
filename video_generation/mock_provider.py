"""
Mock Video Generation Provider for TONY AI (Stage 7).
Generates deterministic, lightweight test MP4 videos using PyAV for development and automated testing.
Does not require internet access, API keys, or GPU hardware.
"""
import io
import time
import logging
from typing import Tuple, Dict, Any, Optional, Callable
import numpy as np
import av
from video_generation.base import VideoProvider
from video_generation.models import VideoGenerationRequest

logger = logging.getLogger("tony.video_generation.mock")


class MockVideoProvider(VideoProvider):
    """Deterministic mock provider that produces playable MP4 video streams."""

    def __init__(self, model_name: str = "mock-video-v1"):
        super().__init__(
            provider_name="mock",
            model_name=model_name,
            supports_text_to_video=True,
            supports_image_to_video=True,
            supports_cancellation=True
        )

    def _render_synthetic_mp4(
        self,
        width: int,
        height: int,
        duration: int,
        fps: int,
        label: str,
        base_color: Tuple[int, int, int] = (20, 30, 45),
        progress_callback: Optional[Callable[[Optional[int], str], None]] = None
    ) -> bytes:
        """Render a synthetic MP4 video in memory using PyAV."""
        # Ensure dimensions are even numbers (required by libx264/yuv420p)
        width = width if width % 2 == 0 else width + 1
        height = height if height % 2 == 0 else height + 1
        total_frames = max(fps, int(duration * fps))

        output_stream = io.BytesIO()
        container = av.open(output_stream, mode="w", format="mp4")
        stream = container.add_stream("libx264", rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"

        # Simple high-tech animated pattern (pulse and moving scanline)
        for frame_idx in range(total_frames):
            frame_img = np.zeros((height, width, 3), dtype=np.uint8)
            # Base color gradient
            frame_img[:, :, 0] = base_color[0]
            frame_img[:, :, 1] = base_color[1]
            frame_img[:, :, 2] = base_color[2]

            # Animated scanline
            scan_y = int((frame_idx / total_frames) * height) % height
            frame_img[max(0, scan_y - 2):min(height, scan_y + 3), :, 0] = 0
            frame_img[max(0, scan_y - 2):min(height, scan_y + 3), :, 1] = 210
            frame_img[max(0, scan_y - 2):min(height, scan_y + 3), :, 2] = 255

            # Center pulse box
            pulse = int(20 * np.sin(2 * np.pi * frame_idx / fps))
            cx, cy = width // 2, height // 2
            half_w, half_h = 40 + pulse, 40 + pulse
            y1, y2 = max(0, cy - half_h), min(height, cy + half_h)
            x1, x2 = max(0, cx - half_w), min(width, cx + half_w)
            frame_img[y1:y2, x1:x2, 1] = np.clip(frame_img[y1:y2, x1:x2, 1] + 80, 0, 255)

            av_frame = av.VideoFrame.from_ndarray(frame_img, format="bgr24")
            for packet in stream.encode(av_frame):
                container.mux(packet)

            if progress_callback and (frame_idx % max(1, total_frames // 4) == 0 or frame_idx == total_frames - 1):
                pct = int(((frame_idx + 1) / total_frames) * 100)
                progress_callback(pct, f"Synthesizing test video: {pct}%")

        # Flush encoder
        for packet in stream.encode():
            container.mux(packet)

        container.close()
        return output_stream.getvalue()

    def generate_text_to_video(
        self,
        request: VideoGenerationRequest,
        progress_callback: Optional[Callable[[Optional[int], str], None]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Synthesize a deterministic test video from prompt."""
        t0 = time.time()
        logger.info(f"MockVideoProvider generating video for prompt: '{request.prompt}'")

        if progress_callback:
            progress_callback(10, "Initializing mock video engine...")

        video_bytes = self._render_synthetic_mp4(
            width=request.width,
            height=request.height,
            duration=request.duration,
            fps=request.fps,
            label=f"TONY AI MOCK VIDEO: {request.prompt[:30]}",
            base_color=(15, 25, 40),
            progress_callback=progress_callback
        )

        elapsed_ms = int((time.time() - t0) * 1000)
        metadata = {
            "provider": self.provider_name,
            "model": self.model_name,
            "simulated": True,
            "generation_time_ms": elapsed_ms,
            "prompt": request.prompt,
            "width": request.width,
            "height": request.height,
            "duration": request.duration,
            "fps": request.fps,
            "format": "mp4"
        }
        return video_bytes, metadata

    def generate_image_to_video(
        self,
        request: VideoGenerationRequest,
        image_bytes: bytes,
        progress_callback: Optional[Callable[[Optional[int], str], None]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Synthesize a video animated from a source image."""
        t0 = time.time()
        logger.info(f"MockVideoProvider animating source image ({len(image_bytes)} bytes)")

        if progress_callback:
            progress_callback(15, "Loading source image frame for animation...")

        # Render simulated animation
        video_bytes = self._render_synthetic_mp4(
            width=request.width,
            height=request.height,
            duration=request.duration,
            fps=request.fps,
            label="TONY AI MOCK IMAGE-TO-VIDEO",
            base_color=(40, 20, 35),
            progress_callback=progress_callback
        )

        elapsed_ms = int((time.time() - t0) * 1000)
        metadata = {
            "provider": self.provider_name,
            "model": self.model_name,
            "simulated": True,
            "generation_time_ms": elapsed_ms,
            "prompt": request.prompt,
            "parent_image_id": request.parent_image_id,
            "width": request.width,
            "height": request.height,
            "duration": request.duration,
            "fps": request.fps,
            "format": "mp4"
        }
        return video_bytes, metadata

    def cancel(self, generation_id: str) -> bool:
        """Simulated cancellation."""
        logger.info(f"Mock video generation '{generation_id}' cancelled.")
        return True

    def check_health(self) -> Dict[str, Any]:
        """Check mock provider readiness."""
        return {
            "available": True,
            "provider": self.provider_name,
            "model": self.model_name,
            "simulated": True,
            "status": "ready",
            "supports_text_to_video": True,
            "supports_image_to_video": True
        }
