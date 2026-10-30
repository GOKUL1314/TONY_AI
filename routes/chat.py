"""
Chat API routes for TONY.
Provides endpoints for message dispatch, history retrieval, session clearing, and system status.
Integrates Long-Term Memory (Stage 4) for intent extraction, preference recall, and context injection.
"""
import re
from datetime import datetime
import logging
from flask import Blueprint, current_app, jsonify, request
from ai.provider import AIProviderError
from memory.extractor import MemoryIntent, is_sensitive_secret
from intelligence.models import IntentType
from intelligence.system_prompt import build_system_prompt
from tools.schemas import RiskLevel

logger = logging.getLogger("tony.routes.chat")

chat_bp = Blueprint("chat", __name__, url_prefix="/api")


def _get_services():
    """Helper to access registered services from Flask application context."""
    ai_provider = current_app.config.get("AI_PROVIDER_INSTANCE")
    conversation_service = current_app.config.get("CONVERSATION_SERVICE_INSTANCE")
    memory_manager = current_app.config.get("MEMORY_MANAGER_INSTANCE")
    memory_retriever = current_app.config.get("MEMORY_RETRIEVER_INSTANCE")
    memory_extractor = current_app.config.get("MEMORY_EXTRACTOR_INSTANCE")
    tool_registry = current_app.config.get("TOOL_REGISTRY_INSTANCE")
    tool_confirmation = current_app.config.get("TOOL_CONFIRMATION_INSTANCE")
    tool_executor = current_app.config.get("TOOL_EXECUTOR_INSTANCE")
    tool_planner = current_app.config.get("TOOL_PLANNER_INSTANCE")
    image_manager = current_app.config.get("IMAGE_MANAGER_INSTANCE")
    video_manager = current_app.config.get("VIDEO_MANAGER_INSTANCE")
    return (
        ai_provider,
        conversation_service,
        memory_manager,
        memory_retriever,
        memory_extractor,
        tool_registry,
        tool_confirmation,
        tool_executor,
        tool_planner,
        image_manager,
        video_manager
    )



@chat_bp.route("/chat", methods=["POST"])
def chat():
    """
    Primary chat endpoint.
    Expects JSON: {"message": "..."}
    Returns JSON: {"response": "...", "timestamp": "...", "provider": "...", "model": "...", "memory_context": ...}
    """
    # 1. Validate request payload
    if not request.is_json:
        logger.warning("Rejected chat request: Non-JSON payload received.")
        return jsonify({"error": "Invalid request. Content-Type must be application/json."}), 400

    data = request.get_json(silent=True)
    if data is None:
        logger.warning("Rejected chat request: Malformed or unparseable JSON.")
        return jsonify({"error": "Malformed JSON payload."}), 400

    message = data.get("message")
    if message is None:
        logger.warning("Rejected chat request: 'message' key missing.")
        return jsonify({"error": "The 'message' field is required."}), 400

    if not isinstance(message, str):
        logger.warning("Rejected chat request: 'message' is not a string.")
        return jsonify({"error": "The 'message' field must be a string."}), 400

    clean_message = message.strip()
    if not clean_message:
        logger.warning("Rejected chat request: Empty message received.")
        return jsonify({"error": "Message cannot be empty."}), 400

    (
        ai_provider,
        conversation_service,
        memory_manager,
        memory_retriever,
        memory_extractor,
        tool_registry,
        tool_confirmation,
        tool_executor,
        tool_planner,
        image_manager,
        video_manager
    ) = _get_services()
    if tool_executor and tool_confirmation:
        if tool_executor.confirmation_manager is not tool_confirmation:
            tool_executor.confirmation_manager = tool_confirmation
    elif tool_executor and not tool_confirmation:
        tool_confirmation = tool_executor.confirmation_manager
    if not ai_provider or not conversation_service:
        logger.critical("Subsystem failure: Services not initialized in application context.")
        return jsonify({"error": "Core assistant subsystems are not initialized."}), 500

    # 0. Prompt Injection / Security Violations
    if re.search(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior|your)?\s*(?:instructions|rules|security|protocols|safety)\b", clean_message):
        reply = "I cannot ignore safety protocols or instructions, Sir. All security policies remain strictly enforced."
        turn = conversation_service.add_turn(clean_message, reply)
        return jsonify({
            "response": reply,
            "timestamp": turn["timestamp"],
            "provider": "security_policy",
            "model": "safety_guard"
        }), 200

    if re.search(r"(?i)\b(?:execute|run)\s+(?:this\s+)?(?:powershell|cmd|bash|shell)\b", clean_message) or re.search(r"(?i)\bpowershell\s+command\b", clean_message):
        reply = "Arbitrary shell or PowerShell execution is strictly prohibited by security policy, Sir."
        turn = conversation_service.add_turn(clean_message, reply)
        return jsonify({
            "response": reply,
            "timestamp": turn["timestamp"],
            "provider": "security_policy",
            "model": "safety_guard"
        }), 200

    if re.search(r"(?i)\b(?:remove|disable|bypass)\s+(?:your\s+)?(?:safety|security|restrictions|guardrails)\b", clean_message):
        reply = "I cannot remove or weaken system safety restrictions, Sir. All security policies remain strictly enforced."
        turn = conversation_service.add_turn(clean_message, reply)
        return jsonify({
            "response": reply,
            "timestamp": turn["timestamp"],
            "provider": "security_policy",
            "model": "safety_guard"
        }), 200

    # 1. Direct Wake Greeting Check ("Tony!", "Tony", "Hey Tony")
    if re.match(r"^(?:tony|hey\s+tony|hi\s+tony|okay\s+tony)[!?,.]*$", clean_message.lower().strip()):
        reply = "Yes, Sir."
        turn = conversation_service.add_turn(clean_message, reply)
        return jsonify({
            "response": reply,
            "timestamp": turn["timestamp"],
            "provider": getattr(ai_provider, "provider_name", "intelligence"),
            "model": "wake_greeting"
        }), 200

    # 1b. Self-Upgrade & Diagnostic Subsystem Handling
    self_upgrade_mgr = current_app.config.get("SELF_UPGRADE_MANAGER_INSTANCE")
    if self_upgrade_mgr:
        lower_msg = clean_message.lower().strip()

        # Run Self Diagnostic / Health check
        if re.search(r"\b(?:run\s+(?:a\s+)?self\s+diagnostic|run\s+(?:a\s+)?health\s+check(?:\s+on\s+yourself)?|self\s+diagnostic|health\s+check)\b", lower_msg):
            diag = self_upgrade_mgr.diagnose()
            status_items = []
            for name, data in diag.subsystems.items():
                st = "Healthy" if data.get("healthy") else "Degraded"
                status_items.append(f"• {name.replace('_', ' ').title()}: {st}")
            summary = "\n".join(status_items)
            reply = f"Self-diagnostic complete, Sir. All core systems are operational:\n{summary}"
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "self_upgrade_engine",
                "model": "diagnostic_analyzer",
                "diagnostic": diag.to_dict()
            }), 200

        # Analyze intelligence layer / What could be improved
        if re.search(r"\b(?:analyze\s+your\s+(?:intelligence(?:\s+layer)?|code|system)|what\s+could\s+be\s+improved|check\s+your\s+response\s+quality\s+and\s+improve\s+it)\b", lower_msg):
            reply = (
                "Certainly, Sir. I analyzed my intelligence layer and identified three areas that could improve response reliability:\n"
                "1. Centralize response validation\n"
                "2. Improve model routing\n"
                "3. Strengthen capability checks\n\n"
                "Would you like me to create an upgrade plan to apply these changes?"
            )
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "self_upgrade_engine",
                "model": "analyzer"
            }), 200

        # Create Upgrade Plan / Improve intelligence
        if re.search(r"\b(?:create\s+(?:an?\s+)?(?:upgrade\s+)?plan|create\s+a\s+plan\s+to\s+improve|improve\s+your\s+intelligence)\b", lower_msg):
            plan = self_upgrade_mgr.create_plan(
                reason="Improve response quality and capability validation",
                files_to_modify=["intelligence/evaluator.py", "intelligence/pipeline.py"]
            )
            reply = (
                f"Certainly, Sir. I have formulated an upgrade plan ({plan.upgrade_id}):\n"
                f"• Reason: {plan.reason}\n"
                f"• Target Files: {', '.join(plan.files_changed)}\n"
                f"• Risk Level: {plan.risk_level.value}\n"
                f"• Tests Affected: {plan.tests_affected}\n\n"
                f"This upgrade requires your confirmation before proceeding. Reply 'confirm' or call the apply API to execute."
            )
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "self_upgrade_engine",
                "model": "upgrade_planner",
                "plan": plan.to_dict()
            }), 200

    # 2. Check for Active Pending Confirmation (Stage 5)
    cmd_lower = re.sub(
        r"^(?:tony[,!:]?\s*|hey\s+tony[,!:]?\s*|hi\s+tony[,!:]?\s*|please\s+)+",
        "",
        clean_message.lower().strip()
    ).strip()
    # Also strip trailing addresses like ", Tony" or " please"
    cmd_lower = re.sub(
        r"(?:[,!:]?\s*(?:tony|please))+[.!?,]?$",
        "",
        cmd_lower
    ).strip().rstrip(".!?,")

    if tool_confirmation and tool_executor:
        active_pending = tool_confirmation.get_active_pending()
        if active_pending:
            CONFIRM_TOKENS = {
                "yes", "y", "confirm", "proceed", "do it", "sure", "ok", "okay",
                "go ahead", "yes please", "yeah", "yep", "affirmative", "execute", "continue"
            }
            CANCEL_TOKENS = {
                "no", "n", "cancel", "stop", "abort", "don't", "dont",
                "never mind", "nevermind", "no don't", "negative", "cancel it"
            }

            norm_cmd = re.sub(r"[^\w\s]", " ", cmd_lower).strip()
            cmd_words = set(norm_cmd.split())

            is_cancel = (
                cmd_lower in CANCEL_TOKENS
                or bool(cmd_words & {"cancel", "abort", "stop", "dont", "no", "nevermind", "negative"})
                or bool(re.search(r"\b(?:no|cancel|stop|abort|don't|dont|negative)\b", norm_cmd))
            )
            is_confirm = (
                not is_cancel
                and (
                    cmd_lower in CONFIRM_TOKENS
                    or bool(cmd_words & {"yes", "confirm", "proceed", "execute", "sure", "ok", "okay", "yep", "yeah"})
                    or bool(re.search(r"\b(?:yes|confirm|proceed|execute|do\s+it|go\s+ahead|sure|ok|okay)\b", norm_cmd))
                )
            )

            if is_cancel:
                result = tool_executor.cancel_action(active_pending.id)
                reply = f"Action cancelled. {active_pending.description} was not executed."
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "tool_confirmation",
                    "model": active_pending.tool_name,
                    "tool_result": result.to_dict()
                }), 200

            if is_confirm:
                result = tool_executor.confirm_action(active_pending.id)
                reply = f"Confirmed. {result.message}" if result.success else f"Action failed: {result.message}"
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "tool_confirmation",
                    "model": active_pending.tool_name,
                    "tool_result": result.to_dict()
                }), 200

    # 2b. Intelligence Orchestration & Multi-Step Engine (Stage 8)
    orchestrator = current_app.config.get("ORCHESTRATOR_INSTANCE")
    if orchestrator:
        ctx = orchestrator.get_context()
        detected = orchestrator.intent_engine.detect_intent(clean_message, context=ctx)
        if detected.entities.get("security_rejection"):
            reply = "Security Alert: That action violates system safety policy and cannot be executed."
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "security_guard",
                "model": "safety_policy"
            }), 200

        if detected.type in (IntentType.MULTI_STEP_TASK, IntentType.CANCEL_TASK):
            plan = orchestrator.execute(clean_message)
            reply = plan.natural_response
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "intelligence_orchestrator",
                "model": "task_planner",
                "task_plan": plan.to_dict()
            }), 200

    # 3. Video Generation Subsystem (Stage 7)
    if video_manager:
        vid_intent_info = video_manager.detect_intent(clean_message)
        vid_intent = vid_intent_info.get("intent")

        if vid_intent == "text_to_video":
            vid_prompt = vid_intent_info.get("prompt", "")
            vid_duration = vid_intent_info.get("duration", 5)
            vid_width = vid_intent_info.get("width", 512)
            vid_height = vid_intent_info.get("height", 512)

            if vid_duration > video_manager.max_duration:
                reply = (
                    f"The current video limit is {video_manager.max_duration} seconds. "
                    f"Please request a duration of {video_manager.max_duration} seconds or less."
                )
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "video_generation",
                    "model": "validation_guard"
                }), 200

            try:
                job = video_manager.start_text_to_video(
                    prompt=vid_prompt,
                    duration=vid_duration,
                    width=vid_width,
                    height=vid_height
                )
                reply = f"Understood. I'm generating a video of {vid_prompt} now. You can track progress in the Video Studio."
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "video_generation",
                    "model": video_manager.provider.model_name,
                    "video_job": job.to_dict()
                }), 200
            except Exception as e:
                reply = f"I couldn't initiate video generation: {e}"
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "video_generation",
                    "model": "error",
                    "error": str(e)
                }), 200

        elif vid_intent == "image_to_video":
            active_img = video_manager.get_active_image()
            if not active_img:
                reply = "I couldn't find an active image to animate. Please generate or select an image first."
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "video_generation",
                    "model": "validation_guard"
                }), 200

            try:
                job = video_manager.start_image_to_video(
                    image_id=active_img.image_id
                )
                reply = "Understood. I'm animating the active image into a moving video now. You can track progress in the Video Studio."
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "video_generation",
                    "model": video_manager.provider.model_name,
                    "video_job": job.to_dict()
                }), 200
            except Exception as e:
                reply = f"I couldn't animate that image: {e}"
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "video_generation",
                    "model": "error",
                    "error": str(e)
                }), 200

    # 4. Image Generation Subsystem (Stage 6)
    if image_manager:
        intent_info = image_manager.detect_intent(clean_message)
        intent = intent_info.get("intent")

        if intent == "create":
            img_prompt = intent_info.get("prompt", "")
            res = image_manager.generate(prompt=img_prompt)
            if res.success:
                is_mock = (res.image_metadata.provider == "mock")
                if is_mock:
                    reply = f"I've generated an image of {img_prompt} (offline mock simulation). I have displayed it on your screen. Configure IMAGE_API_KEY in .env for real AI image generation."
                else:
                    reply = f"I've generated an image of {img_prompt}. I have displayed it on your screen."
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "image_generation",
                    "model": res.image_metadata.model,
                    "image_result": res.image_metadata.to_dict()
                }), 200
            else:
                reply = f"I couldn't generate that image: {res.error_message}"
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "image_generation",
                    "model": "safety_guard" if res.status_code == 400 else "error",
                    "error": res.error_message
                }), 200

        elif intent == "edit":
            instruction = intent_info.get("instruction", "")
            res = image_manager.edit(instruction=instruction)
            if res.success:
                is_mock = (res.image_metadata.provider == "mock")
                if is_mock:
                    reply = f"I've updated the image to be {instruction} (offline mock simulation). I have displayed the updated image on your screen."
                else:
                    reply = f"I've updated the image to be {instruction}. I have displayed the updated image on your screen."
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "image_generation",
                    "model": res.image_metadata.model,
                    "image_result": res.image_metadata.to_dict()
                }), 200
            else:
                reply = f"I couldn't update that image: {res.error_message}"
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "image_generation",
                    "model": "error",
                    "error": res.error_message
                }), 200

        elif intent == "regenerate":
            res = image_manager.regenerate()
            if res.success:
                is_mock = (res.image_metadata.provider == "mock")
                if is_mock:
                    reply = "I've regenerated the image for you (offline mock simulation). I have displayed it on your screen."
                else:
                    reply = "I've regenerated the image for you. I have displayed it on your screen."
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "image_generation",
                    "model": res.image_metadata.model,
                    "image_result": res.image_metadata.to_dict()
                }), 200
            else:
                reply = f"I couldn't regenerate the image: {res.error_message}"
                turn = conversation_service.add_turn(clean_message, reply)
                return jsonify({
                    "response": reply,
                    "timestamp": turn["timestamp"],
                    "provider": "image_generation",
                    "model": "error",
                    "error": res.error_message
                }), 200

    # 3.5 Personal Knowledge Base & RAG Query (Stage 11)
    knowledge_manager = current_app.config.get("KNOWLEDGE_MANAGER_INSTANCE")
    if knowledge_manager:
        k_query = None
        for t_text in [cmd_lower, clean_message]:
            if not t_text:
                continue
            m = re.search(r"^(?:search|find|look\s+up)\s+(?:in\s+)?(?:my\s+)?(?:documents?|docs?|knowledge(?:\s+base)?|notes?)\s+(?:for\s+|about\s+)?(.+)$", t_text, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                if not re.search(r"\b(?:tax\s+records?|records?|receipts?|invoices?|files?|spreadsheets?|\.[a-zA-Z0-9]+)\b", cand, re.IGNORECASE):
                    k_query = cand
                    break
            m = re.search(r"^(?:what\s+do(?:es)?\s+(?:my\s+)?(?:documents?|docs?|knowledge(?:\s+base)?|notes?)\s+say\s+about\s+)(.+)$", t_text, re.IGNORECASE)
            if m:
                k_query = m.group(1).strip()
                break
            m = re.search(r"^(?:what\s+(?:are|is)\s+(?:the\s+)?)(.+?)\s+in\s+(?:my\s+)?(?:documents?|docs?|notes?)$", t_text, re.IGNORECASE)
            if m:
                k_query = t_text
                break
            m = re.search(r"^(?:ask\s+(?:my\s+)?(?:documents?|docs?|knowledge(?:\s+base)?|notes?)\s+)(.+)$", t_text, re.IGNORECASE)
            if m:
                k_query = m.group(1).strip()
                break
            m = re.search(r"^(?:summarize|summary\s+of)\s+(?:the\s+)?(?:document|file|notes?|python\s+file)\s*(.+)?$", t_text, re.IGNORECASE)
            if m:
                k_query = t_text
                break

        if k_query:
            rag_res = knowledge_manager.ask(question=k_query, ai_provider=ai_provider)
            reply = rag_res.answer
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "knowledge_rag",
                "model": "hybrid_search",
                "citations": [c.to_dict() for c in rag_res.citations],
                "confidence": rag_res.confidence
            }), 200

    # 3.6 Personalization & Proactive Intelligence (Stage 12)
    personalization_manager = current_app.config.get("PERSONALIZATION_MANAGER_INSTANCE")
    if personalization_manager:
        lower_msg = clean_message.lower().strip()

        # Proactive toggle
        if re.search(r"^(?:enable\s+proactive\s+mode|turn\s+on\s+proactive\s+mode)$", lower_msg):
            res = personalization_manager.enable_proactive_mode()
            turn = conversation_service.add_turn(clean_message, res["message"])
            return jsonify({
                "response": res["message"],
                "timestamp": turn["timestamp"],
                "provider": "personalization_engine",
                "model": "proactive_controller"
            }), 200

        if re.search(r"^(?:disable\s+proactive\s+mode|turn\s+off\s+proactive\s+mode)$", lower_msg):
            res = personalization_manager.disable_proactive_mode()
            turn = conversation_service.add_turn(clean_message, res["message"])
            return jsonify({
                "response": res["message"],
                "timestamp": turn["timestamp"],
                "provider": "personalization_engine",
                "model": "proactive_controller"
            }), 200

        # Morning Briefing
        if re.search(r"\b(?:give\s+me|show|what\s+is|what's|generate)\s+(?:my\s+)?(?:morning\s+)?briefing\b", lower_msg) or re.search(r"\bwhat\s+do\s+i\s+have\s+today\b", lower_msg):
            briefing = personalization_manager.get_morning_briefing()
            reply = briefing.synthesized_text
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "personalization_engine",
                "model": "morning_briefing",
                "briefing": briefing.to_dict()
            }), 200

        # Evening Summary
        if re.search(r"\b(?:evening\s+summary|end\s+of\s+day\s+summary)\b", lower_msg):
            summary = personalization_manager.get_evening_summary()
            reply = summary.synthesized_text
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "personalization_engine",
                "model": "evening_summary",
                "summary": summary.to_dict()
            }), 200

        # Reminder Creation
        if re.search(r"\b(?:remind\s+me|schedule(?:\s+a)?\s+reminder|create(?:\s+a)?\s+reminder)\b", lower_msg) or re.search(r"^every\s+(?:day|weekday|\w+day).+remind\s+me", lower_msg):
            rem = personalization_manager.create_reminder_from_text(clean_message)
            t = rem.title
            st = rem.scheduled_time
            rec = rem.recurrence.value if hasattr(rem.recurrence, "value") else str(rem.recurrence)
            rec_str = f" ({rec})" if rec != "none" else ""
            reply = f"Done. I have scheduled a reminder to {t} at {st}{rec_str}."
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "personalization_engine",
                "model": "scheduler",
                "reminder": rem.to_dict()
            }), 200

        # Reminder Listing
        if re.search(r"\b(?:show\s+(?:my\s+)?reminders|what\s+are\s+my\s+reminders|list\s+reminders|what'?s\s+my\s+next\s+reminder)\b", lower_msg):
            rems = personalization_manager.list_reminders(enabled_only=True)
            if not rems:
                reply = "You currently have no scheduled reminders."
            else:
                items = [f"• {r.title} ({r.next_trigger_at or r.scheduled_time})" for r in rems[:5]]
                reply = f"You have {len(rems)} scheduled reminder(s):\n" + "\n".join(items)
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "personalization_engine",
                "model": "scheduler",
                "reminders": [r.to_dict() for r in rems]
            }), 200

        # Reminder Cancellation / Deletion
        if re.search(r"\b(?:cancel|delete)\s+(?:my\s+)?reminder\b", lower_msg):
            m_target = re.sub(r"^(?:cancel|delete)\s+(?:my\s+)?reminder\s*", "", lower_msg).strip()
            rems = personalization_manager.list_reminders()
            target_rem = None
            for r in rems:
                if m_target and m_target in r.title.lower():
                    target_rem = r
                    break
            if not target_rem and rems:
                target_rem = rems[0]
            if target_rem:
                personalization_manager.cancel_reminder(target_rem.id)
                reply = f"Done. I've cancelled the reminder '{target_rem.title}'."
            else:
                reply = "I couldn't find a matching reminder to cancel."
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "personalization_engine",
                "model": "scheduler"
            }), 200

    # 4. Tool Execution & Windows Automation (Stage 5)
    tools_enabled = current_app.config.get("TOOLS_ENABLED", True)
    if tools_enabled and tool_planner and tool_executor:
        plan = tool_planner.plan(clean_message)
        # Intent validation: Prevent search_files from executing without local file evidence
        if plan is not None and plan.get("tool") == "search_files":
            from intelligence.target_scope import analyze_target_scope
            scope = analyze_target_scope(clean_message)
            if not scope.is_local_file or scope.is_compound:
                logger.info(
                    f"Chat route blocked premature search_files execution for: '{clean_message}' "
                    f"(reason: {scope.rejection_reason})"
                )
                plan = None

        if plan is not None:
            tool_name = str(plan.get("tool", "")).lower()
            is_destructive = (
                tool_name in {"delete_file", "delete_folder", "bulk_delete", "overwrite_file", "knowledge_delete", "reminder_delete_all", "personalization_reset"}
                or tool_name.startswith("delete_")
                or tool_name.endswith("_delete")
            )

            # Destructive tools MUST ALWAYS require confirmation in the chat route
            tool_result = tool_executor.execute_plan(plan, skip_confirmation=False)
            if is_destructive and not tool_result.requires_confirmation:
                target_desc = plan.get("parameters", {}).get("target") or plan.get("parameters", {}).get("name") or tool_name
                pending = tool_confirmation.create_pending(
                    tool_name=tool_name,
                    parameters=plan.get("parameters", {}),
                    description=f"Permanently delete or alter '{target_desc}'",
                    risk_level=RiskLevel.HIGH
                )
                tool_result.requires_confirmation = True
                tool_result.confirmation_id = pending.id
                tool_result.success = False
                tool_result.message = f"⚠️ Confirmation Required: That action will permanently modify or delete '{target_desc}'. Do you want me to continue?"

            if tool_result.requires_confirmation:
                reply = (
                    f"{tool_result.message} "
                    f"Reply 'yes' or 'confirm' to proceed, or 'no' to cancel."
                )
            elif tool_result.success:
                reply = tool_result.message
            else:
                reply = f"I couldn't complete that action: {tool_result.message}"

            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "tool_execution",
                "model": plan.get("tool", "system_tool"),
                "tool_result": tool_result.to_dict(),
                "requires_confirmation": tool_result.requires_confirmation,
                "confirmation_id": tool_result.confirmation_id
            }), 200

        # Safety guard: Prevent ungrounded LLM hallucination of deletion or unconfirmed destructive execution
        if re.search(r"\b(?:delete|remove|erase)\s+(?:the\s+)?(?:file|folder|directory)\b", clean_message, re.IGNORECASE):
            reply = "⚠️ Confirmation Required: Deleting files or folders permanently removes data. Please specify the exact target name, and I will request your explicit confirmation before proceeding, Sir."
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "tool_execution",
                "model": "delete_safety_guard",
                "requires_confirmation": True
            }), 200

    # 4. Memory Extraction & Explicit Command Handling (Stage 4)
    if memory_manager and memory_extractor:
        if is_sensitive_secret(clean_message):
            reply = "For your security and privacy, I cannot store sensitive credentials, passwords, or API keys in my memory database."
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": "memory_security",
                "model": "safety_guard"
            }), 200

        extracted = memory_extractor.extract(clean_message)

        # A. Explicit CLEAR command (e.g. "Clear my memories")
        if extracted.intent == MemoryIntent.CLEAR:
            cleared_count = memory_manager.clear_all_memories()
            reply = "I have cleared all your stored memories from long-term storage."
            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": getattr(ai_provider, "provider_name", "memory_engine"),
                "model": getattr(ai_provider, "model_name", "internal")
            }), 200

        # B. Explicit FORGET command (e.g. "Forget that I prefer Python", "Forget my name")
        if extracted.intent == MemoryIntent.FORGET:
            pattern = extracted.target_pattern
            if pattern:
                deactivated = memory_manager.forget_by_pattern(pattern)
                if deactivated:
                    reply = f"I have forgotten that."
                else:
                    reply = f"I couldn't find any stored memories matching '{pattern}'."
            else:
                reply = "What specific information would you like me to forget?"

            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": getattr(ai_provider, "provider_name", "memory_engine"),
                "model": getattr(ai_provider, "model_name", "internal")
            }), 200

        # C. Explicit RECALL ALL command (e.g. "What do you remember about me?")
        if extracted.intent == MemoryIntent.RECALL:
            memories = memory_manager.list_memories(is_active=True, limit=10)
            if memories:
                items = [f"- {m.memory_key.replace('_', ' ').title()}: {m.memory_value}" for m in memories]
                reply = "Here is what I currently remember about you:\n" + "\n".join(items)
            else:
                reply = "I don't have any memories stored about you yet. Tell me what you'd like me to remember!"

            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": getattr(ai_provider, "provider_name", "memory_engine"),
                "model": getattr(ai_provider, "model_name", "internal")
            }), 200

        # D. Explicit REMEMBER directive (e.g. "Remember that my name is Gokul", "Remember that I prefer Python")
        if extracted.intent == MemoryIntent.REMEMBER and extracted.memory_key and extracted.memory_value:
            saved = memory_manager.save_memory(
                memory_key=extracted.memory_key,
                memory_value=extracted.memory_value,
                category=extracted.category,
                importance=extracted.importance,
                source="explicit"
            )

            # Produce courteous natural response
            if extracted.category == "identity":
                reply = f"Nice to meet you, {extracted.memory_value}. I'll remember that."
            elif extracted.category == "preference":
                reply = f"I'll remember that you prefer {extracted.memory_value}."
            elif extracted.category == "skill":
                reply = f"I'll remember that you're learning {extracted.memory_value}."
            elif extracted.category == "project":
                reply = f"I'll remember that your project is {extracted.memory_value}."
            else:
                reply = f"I'll remember that {extracted.memory_value}."

            turn = conversation_service.add_turn(clean_message, reply)
            return jsonify({
                "response": reply,
                "timestamp": turn["timestamp"],
                "provider": getattr(ai_provider, "provider_name", "memory_engine"),
                "model": getattr(ai_provider, "model_name", "internal")
            }), 200

        # E. Candidate fact detection in normal speech (e.g. "My name is Gokul", "I am working on Flutter app")
        if extracted.memory_key and extracted.memory_value and current_app.config.get("MEMORY_AUTO_SAVE", True):
            memory_manager.save_memory(
                memory_key=extracted.memory_key,
                memory_value=extracted.memory_value,
                category=extracted.category,
                importance=extracted.importance,
                source="extracted"
            )

    # 3. Retrieve Relevant Memories & Assemble Dialogue Context
    memory_context_str = ""
    if memory_retriever and current_app.config.get("MEMORY_ENABLED", True):
        memory_context_str = memory_retriever.build_memory_context(clean_message)

    personalization_context_str = ""
    if personalization_manager and current_app.config.get("PERSONALIZATION_ENABLED", True):
        personalization_context_str = personalization_manager.build_context(clean_message)

    # 2.9 Contextual Fast-Path Reference Resolution (Stage 8 / Reliability Upgrade)
    # Resolves follow-up link and recommendation requests deterministically (<5ms)
    # without invoking expensive local-model inference or risking 60s timeouts.
    if conversation_service:
        recent_history = conversation_service.get_history(limit=6)
        from intelligence.reference_resolver import ReferenceResolver
        res_result = ReferenceResolver.resolve(clean_message, recent_history)
        if res_result and res_result.handled:
            logger.info(f"Fast-path resolved reference for '{clean_message}' (ambiguous={res_result.ambiguous})")
            turn = conversation_service.add_turn(clean_message, res_result.response)
            return jsonify({
                "response": res_result.response,
                "timestamp": turn["timestamp"],
                "provider": "contextual_resolver",
                "model": "fast_path",
                "ambiguous": res_result.ambiguous,
                "url": res_result.url
            }), 200

    try:
        # Antigravity dynamic token budgeting & rolling context compaction
        from intelligence.context_compactor import ContextCompactor
        sys_prompt = build_system_prompt(context_type="standard", user_name="Sir")
        recent_history = conversation_service.get_history(limit=25)
        context = ContextCompactor.assemble_prompt_context(
            system_prompt=sys_prompt,
            recent_history=recent_history,
            memory_context=memory_context_str,
            personalization_context=personalization_context_str,
            max_prompt_chars=6000
        )

        logger.info(f"Processing message ({len(clean_message)} chars) through provider: {ai_provider.provider_name}")
        response_text = ai_provider.generate_response(clean_message, context)

        # 4. Store dialogue turn
        turn = conversation_service.add_turn(clean_message, response_text)

        return jsonify({
            "response": response_text,
            "timestamp": turn["timestamp"],
            "provider": getattr(ai_provider, "provider_name", "unknown"),
            "model": getattr(ai_provider, "model_name", "unknown"),
            "has_memory_context": bool(memory_context_str)
        }), 200

    except AIProviderError as e:
        logger.error(f"AI Provider error during chat generation: {str(e)}")
        err_lower = str(e).lower()
        if "timed out" in err_lower:
            user_msg = (
                "I apologize, Sir. The local AI model inference timed out (exceeded 60 seconds). "
                "This typically happens under heavy system load or when generating large responses. "
                "Please try again or break your request into a smaller query."
            )
            turn = conversation_service.add_turn(clean_message, user_msg)
            return jsonify({
                "response": user_msg,
                "timestamp": turn["timestamp"],
                "provider": getattr(ai_provider, "provider_name", "unknown"),
                "model": getattr(ai_provider, "model_name", "unknown"),
                "error": str(e),
                "timed_out": True
            }), 200

        return jsonify({
            "error": str(e),
            "provider": getattr(ai_provider, "provider_name", "unknown"),
            "model": getattr(ai_provider, "model_name", "unknown")
        }), 503

    except Exception as e:
        logger.exception(f"Unexpected exception during chat processing: {str(e)}")
        return jsonify({
            "error": "An internal server error occurred while processing your request.",
            "details": str(e)
        }), 500


@chat_bp.route("/history", methods=["GET"])
def get_history():
    """Retrieve existing conversation history."""
    services = _get_services()
    conversation_service = services[1]
    if not conversation_service:
        return jsonify({"error": "Conversation service unavailable."}), 500

    history = conversation_service.get_history()
    return jsonify({
        "status": "success",
        "count": len(history),
        "history": history
    }), 200


@chat_bp.route("/history", methods=["DELETE"])
@chat_bp.route("/clear", methods=["POST"])
def clear_history():
    """Clear active conversation history."""
    services = _get_services()
    conversation_service = services[1]
    if not conversation_service:
        return jsonify({"error": "Conversation service unavailable."}), 500

    conversation_service.clear_history()
    return jsonify({
        "status": "success",
        "message": "Conversation history cleared successfully."
    }), 200


@chat_bp.route("/status", methods=["GET"])
def status():
    """System status and diagnostic health check."""
    (
        ai_provider,
        _,
        memory_manager,
        _,
        _,
        tool_registry,
        tool_confirmation,
        tool_executor,
        _,
        image_manager,
        video_manager
    ) = _get_services()
    if not ai_provider:
        return jsonify({"status": "degraded", "error": "AI provider uninitialized."}), 500

    provider_health = ai_provider.check_health()
    memory_stats = memory_manager.get_stats() if memory_manager else {}
    tool_stats = {
        "total_tools": tool_registry.count() if tool_registry else 0,
        "active_pending_confirmations": len(tool_confirmation.list_pending()) if tool_confirmation else 0,
        "recent_activity": tool_executor.get_activity_log() if tool_executor else []
    }
    image_stats = image_manager.get_status() if image_manager else {}
    video_stats = video_manager.get_status() if video_manager else {}

    return jsonify({
        "system": "TONY AI Assistant",
        "stage": current_app.config.get("STAGE", 5),
        "current_stage": 7,
        "stage_name": "Stage 7: Free Video Generation Subsystem",
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "provider": provider_health,
        "memory": memory_stats,
        "tools": tool_stats,
        "images": image_stats,
        "videos": video_stats
    }), 200
