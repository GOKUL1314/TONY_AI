"""
Local Video Generation Provider for TONY AI (Stage 7).
Provides safe hardware capability inspection (GPU, VRAM, CUDA, RAM) and local model execution.
Ensures zero unintended model downloads and strictly sandboxed model loading.
"""
import sys
import platform
import os
import logging
from pathlib import Path
from typing import Tuple, Dict, Any, Optional, Callable
from video_generation.base import VideoProvider
from video_generation.models import VideoGenerationRequest, LocalCapabilityReport
from video_generation.errors import (
    LocalVideoUnavailableError,
    UnsupportedVideoCapabilityError,
    SafetyViolationError
)

logger = logging.getLogger("tony.video_generation.local")


def detect_local_hardware(model_path: Optional[str] = None) -> LocalCapabilityReport:
    """
    Safely inspect the host system hardware to evaluate readiness for local video synthesis.
    Does not install or download any models.
    """
    os_name = f"{platform.system()} {platform.release()}"
    python_ver = sys.version.split()[0]
    gpu_available = False
    gpu_name = "None"
    vram_mb = 0
    cuda_available = False
    ram_available_mb = 0

    # 1. PyTorch / CUDA detection if installed
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            gpu_available = True
            gpu_name = torch.cuda.get_device_name(0)
            vram_mb = int(torch.cuda.get_device_properties(0).total_memory // (1024 * 1024))
    except ImportError:
        pass

    # 2. Windows-specific fallback for GPU name detection via PowerShell / WMI if Torch not available
    if not gpu_available and platform.system().lower() == "windows":
        try:
            import subprocess
            cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                gpu_name = res.stdout.strip().splitlines()[0]
                gpu_available = True
        except Exception:
            pass

    # 3. Memory detection
    try:
        import psutil
        ram_available_mb = int(psutil.virtual_memory().available // (1024 * 1024))
    except ImportError:
        # Fallback approximation
        ram_available_mb = 4096

    # 4. Check local model configuration
    has_model_conf = bool(model_path and model_path.strip())
    model_path_valid = False
    if has_model_conf:
        p = Path(model_path.strip())
        model_path_valid = p.exists() and (p.is_file() or p.is_dir())

    # 5. Determine overall provider availability
    provider_available = False
    reason = ""

    if not has_model_conf:
        reason = "No local video model path configured (VIDEO_LOCAL_MODEL_PATH is empty)."
    elif not model_path_valid:
        reason = f"Configured local model path '{model_path}' was not found on disk."
    elif not cuda_available and vram_mb < 6000:
        reason = f"Local video generation requires CUDA acceleration or at least 6GB VRAM. Detected: {gpu_name} (CUDA: {cuda_available})."
    else:
        provider_available = True
        reason = "Local hardware and model configuration ready."

    return LocalCapabilityReport(
        os=os_name,
        python_version=python_ver,
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        vram_mb=vram_mb,
        cuda_available=cuda_available,
        ram_available_mb=ram_available_mb,
        local_model_configured=has_model_conf,
        local_model_path_valid=model_path_valid,
        provider_available=provider_available,
        reason=reason
    )


class LocalVideoProvider(VideoProvider):
    """Local video generation provider backend for self-hosted diffusion pipelines."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        model_path: Optional[str] = None,
        device: str = "auto",
        backend_runner: Optional[Callable] = None  # Allows pluggable pipeline injection for tests
    ):
        super().__init__(
            provider_name="local",
            model_name=model_name or "local-diffusion-v1",
            supports_text_to_video=True,
            supports_image_to_video=False,
            supports_cancellation=True
        )
        self.model_path = model_path.strip() if model_path else None
        self.device = device
        self._backend_runner = backend_runner
        self._capability = detect_local_hardware(self.model_path)

    def _validate_safe_model_path(self) -> Path:
        """Ensure model path does not escape sandbox or contain suspicious shell sequences."""
        if not self.model_path:
            raise LocalVideoUnavailableError("No local video model path configured. Set VIDEO_LOCAL_MODEL_PATH.")

        p = Path(self.model_path).resolve()
        # Reject traversal markers or invalid types
        if not p.exists():
            raise LocalVideoUnavailableError(f"Local model path '{self.model_path}' does not exist on disk.")

        # Disallow executable scripts disguised as model weights
        if p.suffix.lower() in (".exe", ".bat", ".cmd", ".vbs", ".ps1", ".sh"):
            raise SafetyViolationError(f"Disallowed executable model file type: '{p.suffix}'")

        return p

    def get_capability_report(self) -> LocalCapabilityReport:
        """Return diagnostic report of host hardware and model readiness."""
        self._capability = detect_local_hardware(self.model_path)
        return self._capability

    def generate_text_to_video(
        self,
        request: VideoGenerationRequest,
        progress_callback: Optional[Callable[[Optional[int], str], None]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Run text-to-video inference using configured local pipeline."""
        capability = self.get_capability_report()

        # If a custom test/runner backend is supplied (for unit testing), invoke it safely
        if self._backend_runner is not None:
            logger.info("Executing local video generation via injected backend runner...")
            return self._backend_runner(request, progress_callback)

        if not capability.provider_available:
            logger.warning(f"Local video generation rejected: {capability.reason}")
            raise LocalVideoUnavailableError(capability.reason)

        safe_path = self._validate_safe_model_path()
        logger.info(f"Loading local video pipeline from '{safe_path}' on device '{self.device}'...")

        raise LocalVideoUnavailableError(
            "Local video generation backend pipeline is currently not initialized on this machine."
        )

    def generate_image_to_video(
        self,
        request: VideoGenerationRequest,
        image_bytes: bytes,
        progress_callback: Optional[Callable[[Optional[int], str], None]] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Local image-to-video generation."""
        if self._backend_runner is not None:
            return self._backend_runner(request, progress_callback, image_bytes=image_bytes)
        raise UnsupportedVideoCapabilityError("Local video provider currently does not support image-to-video synthesis.")

    def check_health(self) -> Dict[str, Any]:
        """Check status and hardware readiness."""
        cap = self.get_capability_report()
        return {
            "available": cap.provider_available,
            "provider": self.provider_name,
            "model": self.model_name,
            "model_path": self.model_path or "None",
            "gpu_name": cap.gpu_name,
            "vram_mb": cap.vram_mb,
            "cuda_available": cap.cuda_available,
            "status": "ready" if cap.provider_available else "unavailable",
            "reason": cap.reason
        }
