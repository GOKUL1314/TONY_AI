"""
Project and Subsystem Analyzer for TONY AI Self-Upgrade Subsystem.
Inspects system health, provider readiness, memory/knowledge integrity, and intelligence layer status.
"""
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

from self_upgrade.models import DiagnosticReport

logger = logging.getLogger("tony.self_upgrade.analyzer")


class ProjectAnalyzer:
    """Evaluates project health and identifies architectural improvement opportunities."""

    def __init__(self, project_root: Path, app_context=None):
        self.project_root = project_root
        self.app_context = app_context

    def run_diagnostic(self) -> DiagnosticReport:
        """
        Inspect live subsystem health across all stages.
        """
        cfg = getattr(self.app_context, "config", {}) if self.app_context else {}
        subsystems: Dict[str, Any] = {}
        issues: List[str] = []
        recommendations: List[str] = []

        # 1. Intelligence Layer
        orch = cfg.get("ORCHESTRATOR_INSTANCE") if isinstance(cfg, dict) else None
        subsystems["intelligence"] = {
            "healthy": orch is not None,
            "status": "online" if orch else "uninitialized",
            "layer": "Stage 8 / Advanced Intelligence"
        }
        if not orch:
            issues.append("Orchestrator instance is not initialized in application context.")
            recommendations.append("Ensure TonyOrchestrator is properly instantiated in app.py.")

        # 2. AI Reasoning Provider
        ai_prov = cfg.get("AI_PROVIDER_INSTANCE") if isinstance(cfg, dict) else None
        ai_healthy = False
        if ai_prov:
            try:
                ai_health = ai_prov.check_health()
                ai_healthy = ai_health.get("available", False)
                subsystems["ai_provider"] = {
                    "healthy": ai_healthy,
                    "provider": getattr(ai_prov, "provider_name", "unknown"),
                    "model": getattr(ai_prov, "model_name", "unknown")
                }
            except Exception as e:
                subsystems["ai_provider"] = {"healthy": False, "error": str(e)}
        else:
            subsystems["ai_provider"] = {"healthy": False, "status": "uninitialized"}

        # 3. Memory Subsystem
        mem_mgr = cfg.get("MEMORY_MANAGER_INSTANCE") if isinstance(cfg, dict) else None
        subsystems["memory"] = {
            "healthy": mem_mgr is not None,
            "stats": mem_mgr.get_stats() if mem_mgr else {}
        }

        # 4. Knowledge & RAG Subsystem
        know_mgr = cfg.get("KNOWLEDGE_MANAGER_INSTANCE") if isinstance(cfg, dict) else None
        subsystems["knowledge"] = {
            "healthy": know_mgr is not None,
            "stats": know_mgr.get_stats() if know_mgr else {}
        }

        # 5. Vision Subsystem
        vis_mgr = cfg.get("VISION_MANAGER_INSTANCE") if isinstance(cfg, dict) else None
        subsystems["vision"] = {
            "healthy": vis_mgr is not None,
            "stats": vis_mgr.check_health() if vis_mgr and hasattr(vis_mgr, "check_health") else (vis_mgr.get_status() if hasattr(vis_mgr, "get_status") else {})
        }

        # 6. Image Generation Subsystem
        img_mgr = cfg.get("IMAGE_MANAGER_INSTANCE") if isinstance(cfg, dict) else None
        subsystems["image_generation"] = {
            "healthy": img_mgr is not None,
            "stats": img_mgr.get_status() if img_mgr else {}
        }

        # 7. Video Generation Subsystem
        vid_mgr = cfg.get("VIDEO_MANAGER_INSTANCE") if isinstance(cfg, dict) else None
        subsystems["video_generation"] = {
            "healthy": vid_mgr is not None,
            "stats": vid_mgr.get_status() if vid_mgr else {}
        }

        # 8. Tools & Windows Automation
        tool_reg = cfg.get("TOOL_REGISTRY_INSTANCE") if isinstance(cfg, dict) else None
        subsystems["tools"] = {
            "healthy": tool_reg is not None,
            "registered_count": tool_reg.count() if tool_reg else 0
        }

        # 9. Personalization & Scheduler
        pers_mgr = cfg.get("PERSONALIZATION_MANAGER_INSTANCE") if isinstance(cfg, dict) else None
        subsystems["personalization"] = {
            "healthy": pers_mgr is not None,
            "stats": pers_mgr.get_stats() if pers_mgr else {}
        }

        # Recommendations based on overall health
        if not recommendations:
            recommendations.append("Centralize response validation and capability checks.")
            recommendations.append("Enhance model routing for task-specific providers.")
            recommendations.append("Ensure regular regression test suite execution.")

        all_healthy = all(s.get("healthy", False) for s in subsystems.values())

        return DiagnosticReport(
            timestamp=datetime.now().isoformat(),
            subsystems=subsystems,
            healthy=all_healthy,
            issues=issues,
            recommendations=recommendations
        )
