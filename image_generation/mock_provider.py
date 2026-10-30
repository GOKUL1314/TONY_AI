"""
Deterministic Mock Image Provider for TONY AI (Stage 6).
Generates valid PNG images offline without external dependencies or network calls.
Ideal for testing, development, and offline execution.
"""
import struct
import zlib
import time
from typing import Tuple, Dict, Any
from image_generation.base import BaseImageProvider
from image_generation.models import ImageGenerationRequest


def create_synthetic_png(width: int = 512, height: int = 512, seed_str: str = "") -> bytes:
    """
    Generate a valid PNG image byte buffer using pure Python standard library.
    Generates a futuristic cybernetic grid with colors derived deterministically from seed_str.
    """
    w = max(32, min(width, 128))
    h = max(32, min(height, 128))

    # Derive theme colors deterministically from seed string hash
    h_val = abs(hash(seed_str))
    base_r = 10 + ((h_val & 0xFF) % 30)
    base_g = 20 + (((h_val >> 8) & 0xFF) % 60)
    base_b = 60 + (((h_val >> 16) & 0xFF) % 120)

    raw_rows = []
    grid_spacing = 16

    for y in range(h):
        row = bytearray([0])  # PNG Filter type 0 (None)
        is_grid_y = (y % grid_spacing == 0)
        y_norm = y / max(h - 1, 1)

        for x in range(w):
            is_grid_x = (x % grid_spacing == 0)
            x_norm = x / max(w - 1, 1)

            if is_grid_x or is_grid_y:
                # Glowing neon grid line
                px_r = min(255, base_r + 40)
                px_g = min(255, base_g + 110)
                px_b = min(255, base_b + 90)
            else:
                # Radial/gradient ambient background
                center_dist = ((x_norm - 0.5) ** 2 + (y_norm - 0.5) ** 2) ** 0.5
                glow = max(0.0, 1.0 - center_dist * 1.4)
                px_r = int(min(255, base_r + 30 * glow))
                px_g = int(min(255, base_g + 50 * glow))
                px_b = int(min(255, base_b + 80 * glow))

            row.extend([px_r, px_g, px_b])

        raw_rows.append(bytes(row))

    # Deflate scanlines
    compressed = zlib.compress(b"".join(raw_rows), level=1)

    # Assemble PNG chunks
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data))
    idat_chunk = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", zlib.crc32(b"IDAT" + compressed))
    iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))

    return signature + ihdr_chunk + idat_chunk + iend_chunk


class MockImageProvider(BaseImageProvider):
    """Offline mock image generator for unit testing and offline development."""

    def __init__(self, model_name: str = "mock-image-v1"):
        super().__init__(provider_name="mock", model_name=model_name)

    def generate_image(self, request: ImageGenerationRequest) -> Tuple[bytes, Dict[str, Any]]:
        t_start = time.time()
        png_bytes = create_synthetic_png(
            width=request.width,
            height=request.height,
            seed_str=request.prompt
        )
        elapsed_ms = int((time.time() - t_start) * 1000)

        metadata = {
            "provider": self.provider_name,
            "model": self.model_name,
            "revised_prompt": request.prompt,
            "generation_time_ms": elapsed_ms,
            "simulated": True
        }
        return png_bytes, metadata

    def check_health(self) -> Dict[str, Any]:
        return {
            "available": True,
            "provider": self.provider_name,
            "model": self.model_name,
            "mode": "deterministic_offline",
            "status": "ready"
        }
