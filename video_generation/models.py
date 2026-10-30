"""
Data models and schemas for TONY AI Video Generation subsystem (Stage 7).
Defines request, metadata, asynchronous job, and hardware capability structures.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any, List


@dataclass
class VideoMetadata:
    """Represents full metadata for a generated video asset."""
    video_id: str
    filename: str
    file_path: str
    url: str
    prompt: str
    thumbnail_url: Optional[str] = None
    thumbnail_path: Optional[str] = None
    revised_prompt: Optional[str] = None
    width: int = 512
    height: int = 512
    duration: int = 5
    fps: int = 16
    format: str = "mp4"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    parent_image_id: Optional[str] = None
    provider: str = "mock"
    model: str = "mock-video-v1"
    generation_time_ms: int = 0
    file_size_bytes: int = 0
    simulated: bool = False
    status: str = "completed"
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoMetadata":
        """Instantiate VideoMetadata from dictionary."""
        return cls(
            video_id=data.get("video_id", ""),
            filename=data.get("filename", ""),
            file_path=data.get("file_path", ""),
            url=data.get("url", ""),
            prompt=data.get("prompt", ""),
            thumbnail_url=data.get("thumbnail_url"),
            thumbnail_path=data.get("thumbnail_path"),
            revised_prompt=data.get("revised_prompt"),
            width=int(data.get("width", 512)),
            height=int(data.get("height", 512)),
            duration=int(data.get("duration", 5)),
            fps=int(data.get("fps", 16)),
            format=data.get("format", "mp4"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            parent_image_id=data.get("parent_image_id"),
            provider=data.get("provider", "mock"),
            model=data.get("model", "unknown"),
            generation_time_ms=int(data.get("generation_time_ms", 0)),
            file_size_bytes=int(data.get("file_size_bytes", 0)),
            simulated=bool(data.get("simulated", False)),
            status=data.get("status", "completed"),
            error=data.get("error")
        )


@dataclass
class VideoGenerationRequest:
    """Request payload for generating a video."""
    prompt: str
    width: int = 512
    height: int = 512
    duration: int = 5
    fps: int = 16
    parent_image_id: Optional[str] = None
    source_image_path: Optional[str] = None
    style: Optional[str] = None
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None
    model: Optional[str] = None
    enhance: bool = True
    provider_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VideoJob:
    """Represents an asynchronous video generation task."""
    generation_id: str
    status: str = "queued"  # queued, processing, completed, failed, cancelled
    progress: Optional[int] = None  # None for indeterminate, 0-100 for determinate
    progress_message: str = "Queued for generation"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    request: Optional[VideoGenerationRequest] = None
    video_metadata: Optional[VideoMetadata] = None
    error: Optional[str] = None
    retries: int = 0
    is_cancelled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generation_id": self.generation_id,
            "status": self.status,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "request": self.request.to_dict() if self.request else None,
            "video": self.video_metadata.to_dict() if self.video_metadata else None,
            "error": self.error,
            "retries": self.retries,
            "is_cancelled": self.is_cancelled
        }


@dataclass
class VideoGenerationResult:
    """Outcome of a video generation request initiation or polling."""
    success: bool
    job: Optional[VideoJob] = None
    video_metadata: Optional[VideoMetadata] = None
    error_message: Optional[str] = None
    status_code: int = 200

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "job": self.job.to_dict() if self.job else None,
            "video": self.video_metadata.to_dict() if self.video_metadata else None,
            "error": self.error_message,
            "status_code": self.status_code
        }


@dataclass
class LocalCapabilityReport:
    """Diagnostics and capability assessment for local video generation."""
    os: str
    python_version: str
    gpu_available: bool
    gpu_name: str
    vram_mb: int
    cuda_available: bool
    ram_available_mb: int
    local_model_configured: bool
    local_model_path_valid: bool
    provider_available: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
