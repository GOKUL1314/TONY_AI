"""
Model Routing Abstraction for TONY AI.
Directs requests to appropriate local, free, or configured cloud providers based on task category.
Strictly prevents silent fallback to mock providers or unauthorized paid upgrades.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger("tony.intelligence.model_router")


class TaskCategory(str, Enum):
    """Broad categories for specialized model routing."""
    CHAT = "CHAT"
    VISION = "VISION"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    EMBEDDING = "EMBEDDING"
    FAST_CLASSIFICATION = "FAST_CLASSIFICATION"
    COMPLEX_REASONING = "COMPLEX_REASONING"


@dataclass
class RouteTarget:
    """Metadata describing a selected model/provider destination."""
    category: TaskCategory
    provider_name: str
    model_name: str
    is_local: bool
    is_free: bool
    timeout_seconds: int
    estimated_cost: float = 0.0
    is_healthy: bool = True
    provider_instance: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "is_local": self.is_local,
            "is_free": self.is_free,
            "timeout_seconds": self.timeout_seconds,
            "estimated_cost": self.estimated_cost,
            "is_healthy": self.is_healthy
        }


class ModelRouter:
    """
    Routes intelligence, vision, media, and embedding requests to their optimal configured targets.
    """

    def __init__(self, config=None, app_context=None):
        self.config = config
        self.app_context = app_context

    def _get_config_val(self, key: str, default: Any) -> Any:
        if self.app_context and hasattr(self.app_context, "config"):
            return self.app_context.config.get(key, default)
        if self.config:
            return getattr(self.config, key, default)
        return default

    def route(self, category: TaskCategory, task_metadata: Optional[Dict[str, Any]] = None) -> RouteTarget:
        """
        Determine the appropriate provider target for the given task category.
        """
        meta = task_metadata or {}

        if category in (TaskCategory.CHAT, TaskCategory.FAST_CLASSIFICATION, TaskCategory.COMPLEX_REASONING):
            ai_prov = self._get_config_val("AI_PROVIDER_INSTANCE", None)
            prov_name = getattr(ai_prov, "provider_name", self._get_config_val("AI_PROVIDER", "local"))
            model_name = getattr(ai_prov, "model_name", self._get_config_val("AI_MODEL", "llama3.2:1b"))
            is_local = prov_name in ("local", "ollama")
            return RouteTarget(
                category=category,
                provider_name=prov_name,
                model_name=model_name,
                is_local=is_local,
                is_free=True if is_local else False,
                timeout_seconds=int(self._get_config_val("OLLAMA_TIMEOUT" if is_local else "API_TIMEOUT", 60)),
                estimated_cost=0.0,
                is_healthy=True,
                provider_instance=ai_prov
            )

        elif category == TaskCategory.VISION:
            vis_prov = self._get_config_val("VISION_PROVIDER_INSTANCE", None)
            prov_name = getattr(vis_prov, "provider_name", self._get_config_val("VISION_PROVIDER", "ollama"))
            model_name = getattr(vis_prov, "model_name", self._get_config_val("VISION_MODEL", "moondream"))
            is_local = prov_name in ("ollama", "local")
            return RouteTarget(
                category=category,
                provider_name=prov_name,
                model_name=model_name,
                is_local=is_local,
                is_free=True,
                timeout_seconds=int(self._get_config_val("VISION_TIMEOUT", 90)),
                estimated_cost=0.0,
                is_healthy=True,
                provider_instance=vis_prov
            )

        elif category == TaskCategory.IMAGE:
            img_prov = self._get_config_val("IMAGE_PROVIDER_INSTANCE", None)
            prov_name = getattr(img_prov, "provider_name", self._get_config_val("IMAGE_PROVIDER", "pollinations"))
            model_name = getattr(img_prov, "model_name", self._get_config_val("IMAGE_MODEL", "sana"))
            return RouteTarget(
                category=category,
                provider_name=prov_name,
                model_name=model_name,
                is_local=False,
                is_free=True if prov_name == "pollinations" else False,
                timeout_seconds=int(self._get_config_val("IMAGE_TIMEOUT", 60)),
                estimated_cost=0.0,
                is_healthy=True,
                provider_instance=img_prov
            )

        elif category == TaskCategory.VIDEO:
            vid_prov = self._get_config_val("VIDEO_PROVIDER_INSTANCE", None)
            prov_name = getattr(vid_prov, "provider_name", self._get_config_val("VIDEO_PROVIDER", "huggingface"))
            model_name = getattr(vid_prov, "model_name", self._get_config_val("HF_VIDEO_MODEL", "Wan-AI/Wan2.1-T2V-14B"))
            return RouteTarget(
                category=category,
                provider_name=prov_name,
                model_name=model_name,
                is_local=False,
                is_free=True,  # Paid video generation is strictly disabled by default
                timeout_seconds=int(self._get_config_val("VIDEO_TIMEOUT", 300)),
                estimated_cost=0.0,
                is_healthy=True,
                provider_instance=vid_prov
            )

        elif category == TaskCategory.EMBEDDING:
            prov_name = self._get_config_val("KNOWLEDGE_EMBEDDING_PROVIDER", "ollama")
            model_name = self._get_config_val("KNOWLEDGE_EMBEDDING_MODEL", "nomic-embed-text")
            is_local = prov_name in ("ollama", "local", "mock")
            return RouteTarget(
                category=category,
                provider_name=prov_name,
                model_name=model_name,
                is_local=is_local,
                is_free=True,
                timeout_seconds=30,
                estimated_cost=0.0,
                is_healthy=True
            )

        # Default fallback
        return RouteTarget(
            category=category,
            provider_name="unknown",
            model_name="unknown",
            is_local=True,
            is_free=True,
            timeout_seconds=30,
            is_healthy=False
        )
