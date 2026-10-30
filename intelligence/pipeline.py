"""
Central Intelligence Pipeline for TONY AI.
Orchestrates the entire reasoning and response lifecycle:
receive -> detect_intent -> build_context -> check_capabilities -> route_model
-> execute_or_generate -> evaluate_response -> recover_if_needed -> finalize_response.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

from intelligence.models import Intent, IntentType
from intelligence.system_prompt import build_system_prompt
from intelligence.capabilities import CapabilityRegistry, CapabilityStatus
from intelligence.model_router import ModelRouter, TaskCategory, RouteTarget
from intelligence.evaluator import SelfEvaluator, EvaluationResult
from intelligence.recovery import ErrorRecoveryManager, FailureType, FailureAnalysis
from intelligence.responses import NaturalResponseEngine

logger = logging.getLogger("tony.intelligence.pipeline")


@dataclass
class PipelineResult:
    """End-to-end outcome of an execution through the IntelligencePipeline."""
    response_text: str
    intent: Intent
    route_target: RouteTarget
    evaluation: EvaluationResult
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    revisions_performed: int = 0
    failure_analysis: Optional[FailureAnalysis] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "response_text": self.response_text,
            "intent": self.intent.to_dict(),
            "route_target": self.route_target.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "tool_results": self.tool_results,
            "revisions_performed": self.revisions_performed,
            "failure_analysis": self.failure_analysis.to_dict() if self.failure_analysis else None,
            "metadata": self.metadata
        }


class IntelligencePipeline:
    """
    Central reasoning and dispatch pipeline connecting intelligence components
    with strict isolation, capability boundaries, and self-evaluation.
    """

    MAX_REVISIONS = 2

    def __init__(
        self,
        ai_provider=None,
        tool_registry=None,
        tool_executor=None,
        memory_manager=None,
        memory_retriever=None,
        knowledge_manager=None,
        personalization_manager=None,
        app_context=None
    ):
        self.ai_provider = ai_provider
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.memory_manager = memory_manager
        self.memory_retriever = memory_retriever
        self.knowledge_manager = knowledge_manager
        self.personalization_manager = personalization_manager
        self.app_context = app_context

        # Subsystems
        from intelligence.intent import IntentEngine
        self.intent_engine = IntentEngine(tool_registry=self.tool_registry)
        self.capabilities = CapabilityRegistry(app_context=self.app_context)
        self.router = ModelRouter(app_context=self.app_context)
        self.evaluator = SelfEvaluator(capability_registry=self.capabilities)
        self.response_engine = NaturalResponseEngine()

    def receive(self, raw_message: str) -> str:
        """Sanitize and validate incoming raw user request."""
        if not raw_message or not isinstance(raw_message, str):
            return ""
        return raw_message.strip()

    def detect_intent(self, text: str, context=None) -> Intent:
        """Classify user intent with security checks."""
        return self.intent_engine.detect_intent(text, context=context)

    def build_context(self, user_request: str, intent: Intent, recent_turns: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
        """
        Assemble layered context prioritizing relevance while strictly isolating
        untrusted memory and document RAG data to prevent prompt injection and context bloat.
        """
        context_items: List[Dict[str, str]] = []

        # 1. System Prompt (Highest Priority - Authoritative)
        system_text = build_system_prompt(context_type="standard", user_name="Sir")
        context_items.append({"role": "system", "message": system_text})

        # 2. Relevant Memory Context (Untrusted user data - marked clearly)
        if self.memory_retriever:
            mem_text = self.memory_retriever.build_memory_context(user_request)
            if mem_text and mem_text.strip():
                context_items.append({
                    "role": "system",
                    "message": f"[UNTRUSTED RETRIEVED MEMORY DATA - STRICTLY ADVISORY]:\n{mem_text.strip()}"
                })

        # 3. Relevant Personalization Context
        if self.personalization_manager:
            pers_text = self.personalization_manager.build_context(user_request)
            if pers_text and pers_text.strip():
                context_items.append({
                    "role": "system",
                    "message": f"[PERSONALIZATION CONTEXT]:\n{pers_text.strip()}"
                })

        # 4. Relevant Conversation Turns (Last 6 turns to avoid context bloat)
        if recent_turns:
            limited_turns = recent_turns[-6:]
            for turn in limited_turns:
                context_items.append(turn)

        return context_items

    def check_capabilities(self, intent: Intent) -> CapabilityStatus:
        """Verify whether required tools/subsystems are available."""
        if intent.type in (IntentType.IMAGE_GENERATION, IntentType.IMAGE_EDIT, IntentType.IMAGE_REGENERATE):
            return self.capabilities.check_capability("image_generation", self.app_context)
        if intent.type in (IntentType.VIDEO_GENERATION, IntentType.IMAGE_TO_VIDEO):
            return self.capabilities.check_capability("video_generation", self.app_context)
        if intent.type in (IntentType.VISION_ANALYZE, IntentType.VISION_OCR, IntentType.VISION_DESCRIBE, IntentType.VISION_QUESTION):
            return self.capabilities.check_capability("vision", self.app_context)
        if intent.type in (IntentType.KNOWLEDGE_SEARCH, IntentType.KNOWLEDGE_QUERY, IntentType.KNOWLEDGE_INGEST):
            return self.capabilities.check_capability("knowledge", self.app_context)
        return CapabilityStatus.AVAILABLE

    def route_model(self, intent: Intent) -> RouteTarget:
        """Select appropriate route category."""
        if intent.type in (IntentType.IMAGE_GENERATION, IntentType.IMAGE_EDIT, IntentType.IMAGE_REGENERATE):
            cat = TaskCategory.IMAGE
        elif intent.type in (IntentType.VIDEO_GENERATION, IntentType.IMAGE_TO_VIDEO):
            cat = TaskCategory.VIDEO
        elif intent.type in (IntentType.VISION_ANALYZE, IntentType.VISION_OCR, IntentType.VISION_DESCRIBE, IntentType.VISION_QUESTION):
            cat = TaskCategory.VISION
        else:
            cat = TaskCategory.CHAT

        return self.router.route(cat)

    def execute_or_generate(
        self,
        clean_text: str,
        intent: Intent,
        route_target: RouteTarget,
        context: List[Dict[str, str]]
    ) -> str:
        """Execute action or generate LLM response."""
        # A. Wake word greeting
        if intent.entities.get("wake_greeting"):
            return "Yes, Sir."

        # B. Pure LLM generation
        provider = route_target.provider_instance or self.ai_provider
        if not provider:
            return "I apologize, Sir, but the language reasoning provider is currently offline."

        return provider.generate_response(clean_text, context)

    def evaluate_response(
        self,
        candidate_response: str,
        user_request: str,
        tool_results: Optional[List[Dict[str, Any]]] = None
    ) -> EvaluationResult:
        """Evaluate candidate response for factual truthfulness, hallucination, and safety."""
        return self.evaluator.evaluate_response(
            candidate_response=candidate_response,
            user_request=user_request,
            actual_tool_results=tool_results
        )

    def recover_if_needed(
        self,
        candidate_response: str,
        evaluation: EvaluationResult,
        user_request: str,
        context: List[Dict[str, str]],
        route_target: RouteTarget
    ) -> str:
        """
        Revise response if self-evaluation detected critical issues (maximum 2 revisions).
        """
        current_text = candidate_response
        revisions = 0

        while evaluation.needs_revision and revisions < self.MAX_REVISIONS:
            revisions += 1
            logger.info(f"Self-evaluation flagged issues ({evaluation.issues}). Initiating revision attempt {revisions}/{self.MAX_REVISIONS}.")

            # If secret exposure was flagged, redact immediately
            if any("secret" in is_str.lower() for is_str in evaluation.issues):
                return "For your security, I have withheld sensitive credential details from this response, Sir."

            # Request LLM correction
            revision_prompt = (
                f"Your previous response had the following issue(s): {'; '.join(evaluation.issues)}. "
                f"Please provide an accurate, concise, grounded response to: '{user_request}'. "
                f"Do NOT claim an action succeeded unless it was truly executed."
            )
            try:
                provider = route_target.provider_instance or self.ai_provider
                if provider:
                    revised_text = provider.generate_response(revision_prompt, context)
                    new_eval = self.evaluate_response(revised_text, user_request)
                    if new_eval.passed or new_eval.confidence > evaluation.confidence:
                        current_text = revised_text
                        evaluation = new_eval
            except Exception as e:
                logger.warning(f"Revision generation encountered error: {e}")
                break

        return current_text

    def finalize_response(self, text: str, user_name: str = "Sir") -> str:
        """Apply final JARVIS polish ensuring respectful address without unnatural repetition."""
        cleaned = text.strip()
        if not cleaned:
            return f"I'm at your service, {user_name}."
        return cleaned

    def process(self, raw_message: str, recent_turns: Optional[List[Dict[str, str]]] = None) -> PipelineResult:
        """
        Execute full end-to-end pipeline run.
        """
        # 1. Receive
        clean_text = self.receive(raw_message)

        # 2. Detect Intent
        intent = self.detect_intent(clean_text)

        # 3. Check Capabilities
        cap_status = self.check_capabilities(intent)
        if cap_status == CapabilityStatus.UNAVAILABLE:
            msg = f"I'm unable to perform that action because the required subsystem is unavailable, Sir."
            return PipelineResult(
                response_text=msg,
                intent=intent,
                route_target=self.router.route(TaskCategory.CHAT),
                evaluation=EvaluationResult(passed=True, confidence=1.0)
            )

        # 4. Route Model
        route = self.route_model(intent)

        # 5. Build Context
        context = self.build_context(clean_text, intent, recent_turns=recent_turns)

        # 6. Execute / Generate
        raw_response = self.execute_or_generate(clean_text, intent, route, context)

        # 7. Evaluate Response
        eval_result = self.evaluate_response(raw_response, clean_text)

        # 8. Recover / Revise if needed (max 2 attempts)
        revised_response = raw_response
        revisions = 0
        if eval_result.needs_revision:
            revised_response = self.recover_if_needed(raw_response, eval_result, clean_text, context, route)
            eval_result = self.evaluate_response(revised_response, clean_text)
            revisions = 1

        # 9. Finalize Response
        final_text = self.finalize_response(revised_response)

        return PipelineResult(
            response_text=final_text,
            intent=intent,
            route_target=route,
            evaluation=eval_result,
            revisions_performed=revisions
        )
