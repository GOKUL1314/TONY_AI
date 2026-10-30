"""
Data models and schemas for TONY AI Image Generation subsystem (Stage 6).
Defines request, metadata, and result structures.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class ImageMetadata:
    """Represents full metadata for a generated image."""
    image_id: str
    filename: str
    file_path: str
    url: str
    prompt: str
    revised_prompt: Optional[str] = None
    width: int = 1024
    height: int = 1024
    format: str = "png"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    parent_image_id: Optional[str] = None
    provider: str = "mock"
    model: str = "dall-e-3"
    generation_time_ms: int = 0
    file_size_bytes: int = 0
    simulated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImageMetadata":
        """Instantiate ImageMetadata from dictionary."""
        prov = data.get("provider", "mock")
        is_sim = data.get("simulated")
        if is_sim is None:
            is_sim = (prov == "mock")
        return cls(
            image_id=data.get("image_id", ""),
            filename=data.get("filename", ""),
            file_path=data.get("file_path", ""),
            url=data.get("url", ""),
            prompt=data.get("prompt", ""),
            revised_prompt=data.get("revised_prompt"),
            width=int(data.get("width", 1024)),
            height=int(data.get("height", 1024)),
            format=data.get("format", "png"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            parent_image_id=data.get("parent_image_id"),
            provider=prov,
            model=data.get("model", "unknown"),
            generation_time_ms=int(data.get("generation_time_ms", 0)),
            file_size_bytes=int(data.get("file_size_bytes", 0)),
            simulated=bool(is_sim)
        )


@dataclass
class ImageGenerationRequest:
    """Request payload for generating an image."""
    prompt: str
    width: int = 1024
    height: int = 1024
    parent_image_id: Optional[str] = None
    style: Optional[str] = None
    enhance: bool = True
    provider_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImageEditRequest:
    """Request payload for editing or refining a previous image."""
    edit_instruction: str
    image_id: Optional[str] = None
    width: int = 1024
    height: int = 1024

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImageGenerationResult:
    """Outcome of an image generation operation."""
    success: bool
    image_metadata: Optional[ImageMetadata] = None
    error_message: Optional[str] = None
    status_code: int = 200

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "image": self.image_metadata.to_dict() if self.image_metadata else None,
            "error": self.error_message,
            "status_code": self.status_code
        }
