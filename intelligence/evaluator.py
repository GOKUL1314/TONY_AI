"""
Self-Evaluation Engine for TONY AI.
Inspects candidate LLM and agent responses for hallucinations, capability mismatches,
unsupported claims, and safety risks.
NOTE: Evaluator outputs are STRICTLY ADVISORY and have read-only inspection boundaries.
It cannot modify system prompts, security policies, confirmation gates, memory, or knowledge.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

logger = logging.getLogger("tony.intelligence.evaluator")

# Regex indicators for suspicious unsupported action claims
ACTION_CLAIM_PATTERNS = [
    (re.compile(r"\b(?:i(?:'ve| have)? (?:created|generated|made|saved|deleted|moved|copied|executed|sent|scheduled))\b", re.IGNORECASE), "claimed_action"),
    (re.compile(r"\b(?:here is your (?:image|video|file|download))\b", re.IGNORECASE), "claimed_asset_delivery"),
    (re.compile(r"\b(?:i set a reminder|reminder has been set|reminder scheduled)\b", re.IGNORECASE), "claimed_reminder"),
]

# Sensitive patterns that must never be exposed
SECRET_EXPOSURE_PATTERNS = [
    re.compile(r"\b(?:api[_-]?key|secret[_-]?key|password|bearer\s+[a-zA-Z0-9_\-\.]{15,}|hf_[a-zA-Z0-9]{20,})\b", re.IGNORECASE),
]


@dataclass
class EvaluationResult:
    """Structured inspection outcome from response evaluation."""
    passed: bool
    confidence: float
    issues: List[str] = field(default_factory=list)
    needs_revision: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "confidence": round(self.confidence, 2),
            "issues": self.issues,
            "needs_revision": self.needs_revision,
            "details": self.details
        }


class SelfEvaluator:
    """
    Evaluates responses and tool executions for quality, truthfulness, and safety compliance.
    Read-only and advisory.
    """

    def __init__(self, capability_registry=None):
        self.capability_registry = capability_registry

    def evaluate_response(
        self,
        candidate_response: str,
        user_request: str,
        actual_tool_results: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> EvaluationResult:
        """
        Inspect a candidate response before it is returned to the user.

        :param candidate_response: The draft response text
        :param user_request: The original user request
        :param actual_tool_results: List of actual executed tool results (authoritative source of truth)
        :param context: Supplemental metadata
        :return: EvaluationResult
        """
        if not candidate_response or not candidate_response.strip():
            return EvaluationResult(
                passed=False,
                confidence=0.0,
                issues=["Response is empty or whitespace."],
                needs_revision=True
            )

        issues: List[str] = []
        conf_deductions = 0.0

        tool_results = actual_tool_results or []
        has_executed_tools = len(tool_results) > 0
        all_tools_successful = all(t.get("success", True) for t in tool_results) if has_executed_tools else False

        # 1. Secret / Credential Leakage Check
        for pat in SECRET_EXPOSURE_PATTERNS:
            if pat.search(candidate_response):
                issues.append("CRITICAL: Candidate response appears to expose API keys or passwords.")
                conf_deductions += 0.8
                return EvaluationResult(
                    passed=False,
                    confidence=0.1,
                    issues=issues,
                    needs_revision=True,
                    details={"security_violation": "secret_exposure"}
                )

        # 2. Unsupported Action Claims (Hallucination Detection)
        # If the LLM claims to have done an action, but no tool was executed or the tool failed
        for pat, label in ACTION_CLAIM_PATTERNS:
            if pat.search(candidate_response):
                if not has_executed_tools:
                    # Claimed an action with 0 tool execution
                    # Check if it was a purely conversational query
                    lower_req = user_request.lower()
                    action_words = ["create", "generate", "delete", "move", "open", "remind", "schedule", "save", "video", "image"]
                    if any(w in lower_req for w in action_words):
                        issues.append("Hallucination: Response claims an action succeeded when no tool was executed.")
                        conf_deductions += 0.4
                elif not all_tools_successful:
                    # Tools were executed, but one or more failed, yet response claimed success
                    issues.append("Tool Mismatch: Response claims success despite underlying tool failure.")
                    conf_deductions += 0.5

        # 3. Internal System Detail Exposure
        internal_traces = ["traceback", "file \"c:\\", "exception in thread", "sqlite3.operationalerror"]
        for trace in internal_traces:
            if trace in candidate_response.lower():
                issues.append("Internal Error Trace: Response exposes raw backend exception details.")
                conf_deductions += 0.3

        # 4. Capability Mismatch Check
        if self.capability_registry:
            caps = self.capability_registry.get_capabilities()
            if "video" in user_request.lower() and not caps.get("video_generation", {}).get("available", False):
                if "generating video" in candidate_response.lower() or "created the video" in candidate_response.lower():
                    issues.append("Capability Mismatch: Claimed video generation when provider is unavailable.")
                    conf_deductions += 0.5

        # 5. Excessive Verbosity / Repetition Check
        words = candidate_response.split()
        if len(words) > 1200:
            issues.append("Verbosity: Response exceeds recommended desktop assistant response length.")
            conf_deductions += 0.1

        # Check for immediate consecutive duplicate sentences
        sentences = [s.strip() for s in re.split(r'[.!?]+', candidate_response) if len(s.strip()) > 10]
        if len(sentences) >= 2:
            for i in range(len(sentences) - 1):
                if sentences[i].lower() == sentences[i + 1].lower():
                    issues.append("Repetition: Consecutive duplicate sentence detected.")
                    conf_deductions += 0.15
                    break

        confidence = max(0.0, 1.0 - conf_deductions)
        passed = (len(issues) == 0) and (confidence >= 0.75)
        needs_revision = not passed

        return EvaluationResult(
            passed=passed,
            confidence=confidence,
            issues=issues,
            needs_revision=needs_revision,
            details={"deductions": conf_deductions}
        )
