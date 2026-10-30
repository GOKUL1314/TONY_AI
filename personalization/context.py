"""
Personalized Context Engine for TONY AI (Stage 12).
Extracts strictly relevant user preferences, style attributes, and routine context
for injection into dialogue prompts without causing context bloat.
"""
import re
import logging
from typing import Dict, Any, List, Optional
from personalization.storage import PersonalizationDatabase
from personalization.models import UserProfile

logger = logging.getLogger("tony.personalization.context")


class PersonalizationContextBuilder:
    """Selectively constructs compact personalization prompts tailored to the user's immediate request."""

    def __init__(self, db: PersonalizationDatabase):
        self.db = db

    def build_context(self, user_message: str = "", query: Optional[str] = None) -> str:
        """
        Produce a concise personalization context string relevant to the current query.
        Returns empty string if no personalization is applicable.
        """
        msg = query if query is not None else user_message
        profile = self.db.get_profile()
        msg_lower = (msg or "").lower()

        relevant_directives: List[str] = []

        # 1. User Name and Address
        if profile.preferred_name and profile.preferred_name.lower() not in ("user", "unknown"):
            relevant_directives.append(f"Address the user politely as {profile.preferred_name} (preferred address: {profile.preferred_address}).")

        # Tone persona
        if profile.tone:
            relevant_directives.append(f"Maintain tone persona: {profile.tone}.")

        # 2. Learning / Educational inquiries
        is_learning = bool(re.search(r"\b(?:teach|learn|explain|how\s+to|what\s+is|study|tutorial|guide|course|code|python|dart|javascript)\b", msg_lower))
        if is_learning and profile.learning_style:
            if profile.learning_style == "step_by_step":
                relevant_directives.append("The user prefers step-by-step explanations with clear incremental phases.")
            elif profile.learning_style == "hands_on":
                relevant_directives.append("The user prefers hands-on code examples and practical implementation.")
            elif profile.learning_style == "concise":
                relevant_directives.append("The user prefers concise technical bullet points without fluff.")

        # 3. Response Length & Formality
        if profile.response_length:
            if profile.response_length in ("short", "concise"):
                relevant_directives.append("Keep the response concise and directly to the point.")
            elif profile.response_length in ("detailed", "verbose"):
                relevant_directives.append("Provide a thorough, comprehensive response.")

        if profile.response_style:
            if profile.response_style == "clear_and_direct":
                relevant_directives.append("Use a composed, direct, and structured tone.")
            elif profile.response_style in ("concise", "short"):
                relevant_directives.append("Maintain a concise and punchy communication style.")
            elif profile.response_style == "friendly":
                relevant_directives.append("Maintain an encouraging and approachable tone.")

        # 4. Preferred Language
        if profile.preferred_language and profile.preferred_language.lower() != "english":
            relevant_directives.append(f"Respond in {profile.preferred_language}.")

        # 5. Check relevant custom preferences
        prefs = self.db.list_preferences()
        for p in prefs:
            if p.key in msg_lower or (p.category == "learning" and is_learning):
                relevant_directives.append(f"User preference ({p.key}): {p.value}.")

        if not relevant_directives:
            return ""

        joined = " ".join(relevant_directives)
        return f"[User Personalization Directives: {joined}]"
