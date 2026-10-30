"""
Data Models for TONY AI Vision Subsystem (Stage 9).
Defines structured classes for vision analysis requests, results, tasks, and image metadata.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional
import uuid


class VisionTaskType(str, Enum):
    """Types of visual analysis tasks."""
    ANALYZE = "analyze"
    DESCRIBE = "describe"
    QUESTION = "question"
    OCR = "ocr"


@dataclass
class VisionAnalysisRequest:
    """Request payload for vision operations."""
    image_bytes: Optional[bytes] = None
    image_path: Optional[Path] = None
    image_id: Optional[str] = None
    prompt: str = ""
    task: VisionTaskType = VisionTaskType.ANALYZE
    temperature: float = 0.2
    max_tokens: int = 500
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VisionResult:
    """Structured response from vision inference."""
    vision_id: str
    provider: str
    model: str
    task: str
    prompt: str
    response: str
    image_id: Optional[str] = None
    image_filename: Optional[str] = None
    file_path: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    simulated: bool = False
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to JSON-serializable dictionary."""
        return {
            "vision_id": self.vision_id,
            "provider": self.provider,
            "model": self.model,
            "task": self.task,
            "prompt": self.prompt,
            "response": self.response,
            "image_id": self.image_id,
            "image_filename": self.image_filename,
            "file_path": self.file_path,
            "timestamp": self.timestamp,
            "simulated": self.simulated,
            "duration_seconds": round(self.duration_seconds, 3),
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisionResult":
        """Instantiate VisionResult from dictionary."""
        return cls(
            vision_id=data.get("vision_id", f"vis_{uuid.uuid4().hex[:8]}"),
            provider=data.get("provider", "unknown"),
            model=data.get("model", "unknown"),
            task=data.get("task", VisionTaskType.ANALYZE.value),
            prompt=data.get("prompt", ""),
            response=data.get("response", ""),
            image_id=data.get("image_id"),
            image_filename=data.get("image_filename"),
            file_path=data.get("file_path"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            simulated=data.get("simulated", False),
            duration_seconds=data.get("duration_seconds", 0.0),
            metadata=data.get("metadata", {})
        )
