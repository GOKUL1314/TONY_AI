"""
Diagnostic CLI tool for TONY AI Video Generation Subsystem (Stage 7).
Run: python -m video_generation.cli
"""
import sys
from config.settings import get_config
from video_generation.provider import get_video_provider
from video_generation.local_provider import detect_local_hardware
from video_generation.safety import mask_secret


def print_video_status():
    """Print clean terminal diagnostic report for TONY AI Video Subsystem."""
    cfg = get_config()
    provider = get_video_provider(cfg)
    local_info = detect_local_hardware(getattr(cfg, "VIDEO_LOCAL_MODEL_PATH", ""))

    print("=" * 60)
    print("                TONY VIDEO STATUS")
    print("=" * 60)
    print(f"Active Provider : {cfg.VIDEO_PROVIDER.upper()}")
    print(f"Free Mode       : {'ENABLED' if not cfg.VIDEO_ALLOW_PAID else 'CUSTOM'}")
    print(f"Paid Fallback   : {'ENABLED' if cfg.VIDEO_ALLOW_PAID else 'DISABLED'}")
    print("-" * 60)
    print("HUGGING FACE:")
    print(f"  Configured    : {'YES' if bool(cfg.HF_TOKEN) else 'NO'}")
    print(f"  Token         : {'PRESENT' if cfg.HF_TOKEN else 'MISSING'}")
    print(f"  Model         : {cfg.HF_VIDEO_MODEL}")
    print(f"  Provider      : {cfg.HF_VIDEO_PROVIDER or 'default'}")
    print("-" * 60)
    print("LOCAL:")
    print(f"  GPU           : {local_info.gpu_name}")
    print(f"  VRAM          : {local_info.vram_mb} MB")
    print(f"  CUDA          : {'YES' if local_info.cuda_available else 'NO'}")
    print(f"  Model Path    : {cfg.VIDEO_LOCAL_MODEL_PATH or 'None'}")
    print(f"  Available     : {'YES' if local_info.provider_available else 'NO'}")
    if not local_info.provider_available:
        print(f"  Reason        : {local_info.reason}")
    print("-" * 60)
    print("MOCK:")
    print("  Available     : YES (PyAV MP4 Synthesizer)")
    print("=" * 60)


if __name__ == "__main__":
    print_video_status()
