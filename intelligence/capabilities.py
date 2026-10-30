"""
Capability Registry and Boundary Awareness Engine for TONY AI.
Maintains authoritative state of what TONY can and cannot perform in real-time,
preventing false claims, hallucinations, and phantom execution.
"""
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger("tony.intelligence.capabilities")


class CapabilityStatus(str, Enum):
    """Authoritative lifecycle status for any TONY subsystem capability."""
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class CapabilityRegistry:
    """Tracks and evaluates live system capabilities across all 12 stages."""

    CORE_CAPABILITIES = [
        "chat",
        "voice",
        "wake_word",
        "memory",
        "knowledge",
        "vision",
        "image_generation",
        "video_generation",
        "windows_tools",
        "agent",
        "personalization",
        "scheduler",
        "self_upgrade"
    ]

    def __init__(self, app_context=None):
        self.app_context = app_context
        self._last_checked = datetime.now().isoformat()

    def list_capabilities(self, app_context=None) -> List[Dict[str, Any]]:
        """Return capabilities as a list of dicts."""
        return list(self.get_capabilities(app_context).values())

    def get_capabilities(self, app_context=None) -> Dict[str, Dict[str, Any]]:
        """
        Inspect live subsystem health and compile the authoritative capability registry.
        """
        ctx = app_context or self.app_context
        config = getattr(ctx, "config", {}) if ctx else {}
        self._last_checked = datetime.now().isoformat()

        caps: Dict[str, Dict[str, Any]] = {}

        # 1. Chat Reasoning
        ai_provider = config.get("AI_PROVIDER_INSTANCE") if isinstance(config, dict) else None
        caps["chat"] = {
            "name": "chat",
            "available": ai_provider is not None,
            "provider": getattr(ai_provider, "provider_name", "offline_mock"),
            "model": getattr(ai_provider, "model_name", "unknown"),
            "status": CapabilityStatus.AVAILABLE.value if ai_provider else CapabilityStatus.UNAVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "General conversational intelligence, reasoning, and instruction following."
        }

        # 2. Voice (STT & TTS)
        stt = config.get("STT_PROVIDER_INSTANCE") if isinstance(config, dict) else None
        tts = config.get("TTS_PROVIDER_INSTANCE") if isinstance(config, dict) else None
        voice_avail = (stt is not None) and (tts is not None)
        caps["voice"] = {
            "name": "voice",
            "available": voice_avail,
            "provider": f"{getattr(stt, 'provider_name', 'none')}/{getattr(tts, 'provider_name', 'none')}",
            "status": CapabilityStatus.AVAILABLE.value if voice_avail else CapabilityStatus.UNAVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "Speech-to-text transcription and text-to-speech audio synthesis."
        }

        # 3. Wake Word
        wake_enabled = config.get("WAKE_WORD_ENABLED", True) if isinstance(config, dict) else True
        caps["wake_word"] = {
            "name": "wake_word",
            "available": bool(wake_enabled),
            "provider": "local_pattern_detector",
            "phrase": config.get("WAKE_WORD", "tony") if isinstance(config, dict) else "tony",
            "status": CapabilityStatus.AVAILABLE.value if wake_enabled else CapabilityStatus.UNAVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "Hands-free voice wake phrase activation."
        }

        # 4. Long-Term Memory
        mem_mgr = config.get("MEMORY_MANAGER_INSTANCE") if isinstance(config, dict) else None
        mem_avail = mem_mgr is not None and config.get("MEMORY_ENABLED", True) if isinstance(config, dict) else True
        caps["memory"] = {
            "name": "memory",
            "available": bool(mem_avail),
            "provider": "sqlite_memory_engine",
            "status": CapabilityStatus.AVAILABLE.value if mem_avail else CapabilityStatus.UNAVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "Long-term episodic and semantic user profile memory."
        }

        # 5. Personal Knowledge & RAG
        know_mgr = config.get("KNOWLEDGE_MANAGER_INSTANCE") if isinstance(config, dict) else None
        know_avail = know_mgr is not None and config.get("KNOWLEDGE_ENABLED", True) if isinstance(config, dict) else True
        caps["knowledge"] = {
            "name": "knowledge",
            "available": bool(know_avail),
            "provider": "fts5_bm25_hybrid_rag",
            "status": CapabilityStatus.AVAILABLE.value if know_avail else CapabilityStatus.UNAVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "Personal document indexing, hybrid search, and citation-grounded RAG."
        }

        # 6. Vision Understanding
        vis_mgr = config.get("VISION_MANAGER_INSTANCE") if isinstance(config, dict) else None
        vis_avail = vis_mgr is not None
        caps["vision"] = {
            "name": "vision",
            "available": vis_avail,
            "provider": getattr(config.get("VISION_PROVIDER_INSTANCE"), "provider_name", "ollama") if isinstance(config, dict) else "ollama",
            "status": CapabilityStatus.AVAILABLE.value if vis_avail else CapabilityStatus.UNAVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "Visual scene understanding, OCR, and descriptive query handling."
        }

        # 7. Image Generation
        img_mgr = config.get("IMAGE_MANAGER_INSTANCE") if isinstance(config, dict) else None
        img_avail = img_mgr is not None
        caps["image_generation"] = {
            "name": "image_generation",
            "available": img_avail,
            "provider": getattr(config.get("IMAGE_PROVIDER_INSTANCE"), "provider_name", "pollinations") if isinstance(config, dict) else "pollinations",
            "status": CapabilityStatus.AVAILABLE.value if img_avail else CapabilityStatus.UNAVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "Text-to-image synthesis, editing, and style variations."
        }

        # 8. Video Generation
        vid_mgr = config.get("VIDEO_MANAGER_INSTANCE") if isinstance(config, dict) else None
        vid_avail = vid_mgr is not None
        caps["video_generation"] = {
            "name": "video_generation",
            "available": vid_avail,
            "provider": getattr(config.get("VIDEO_PROVIDER_INSTANCE"), "provider_name", "huggingface") if isinstance(config, dict) else "huggingface",
            "status": CapabilityStatus.AVAILABLE.value if vid_avail else CapabilityStatus.UNAVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "Text-to-video synthesis and image-to-video cinematic animation."
        }

        # 9. Windows Tools
        tool_reg = config.get("TOOL_REGISTRY_INSTANCE") if isinstance(config, dict) else None
        tool_avail = tool_reg is not None and config.get("TOOLS_ENABLED", True) if isinstance(config, dict) else True
        caps["windows_tools"] = {
            "name": "windows_tools",
            "available": bool(tool_avail),
            "provider": "windows_automation_toolkit",
            "tool_count": tool_reg.count() if tool_reg else 0,
            "status": CapabilityStatus.AVAILABLE.value if tool_avail else CapabilityStatus.UNAVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "Local filesystem, application control, and multimedia automation."
        }

        # 10. Agent Workflows
        agent_mgr = config.get("AGENT_MANAGER_INSTANCE") if isinstance(config, dict) else None
        agent_avail = agent_mgr is not None
        caps["agent"] = {
            "name": "agent",
            "available": agent_avail,
            "provider": "autonomous_step_agent",
            "status": CapabilityStatus.AVAILABLE.value if agent_avail else CapabilityStatus.UNAVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "Autonomous multi-step task planning, execution, and self-correction."
        }

        # 11. Personalization
        pers_mgr = config.get("PERSONALIZATION_MANAGER_INSTANCE") if isinstance(config, dict) else None
        pers_avail = pers_mgr is not None and config.get("PERSONALIZATION_ENABLED", True) if isinstance(config, dict) else True
        caps["personalization"] = {
            "name": "personalization",
            "available": bool(pers_avail),
            "provider": "personalization_engine",
            "status": CapabilityStatus.AVAILABLE.value if pers_avail else CapabilityStatus.UNAVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "Adaptive personality profiles, tone preferences, and briefing synthesis."
        }

        # 12. Scheduler & Reminders
        sched_avail = pers_avail and pers_mgr is not None and hasattr(pers_mgr, "scheduler")
        caps["scheduler"] = {
            "name": "scheduler",
            "available": bool(sched_avail),
            "provider": "background_reminder_scheduler",
            "status": CapabilityStatus.AVAILABLE.value if sched_avail else CapabilityStatus.UNAVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "Time-based alerts, proactive briefings, and recurring task scheduling."
        }

        # 13. Self-Upgrade
        caps["self_upgrade"] = {
            "name": "self_upgrade",
            "available": True,
            "provider": "controlled_software_engineering_subsystem",
            "status": CapabilityStatus.AVAILABLE.value,
            "last_checked": self._last_checked,
            "description": "Protected self-diagnostics, plan generation, test verification, and atomic rollbacks."
        }

        return caps

    def check_capability(self, capability_name: str, app_context=None) -> CapabilityStatus:
        """Query availability status of a single named capability."""
        all_caps = self.get_capabilities(app_context)
        cap = all_caps.get(capability_name.lower().strip())
        if not cap:
            return CapabilityStatus.UNKNOWN
        return CapabilityStatus(cap["status"])
