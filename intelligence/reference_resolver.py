"""
Contextual Reference Resolver and Fast-Path Dispatcher for TONY AI.
Resolves follow-up queries regarding links, recommendations, URLs, and previous
context deterministically in < 5ms, avoiding expensive local LLM inference timeouts.
"""
import re
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from tools.browser.browser import KNOWN_SERVICES

logger = logging.getLogger("tony.intelligence.reference_resolver")

# Canonical course / educational / tech domain mapping for grounded URL resolution
COMMON_PLATFORMS = {
    "coursera": "https://www.coursera.org",
    "udemy": "https://www.udemy.com",
    "edx": "https://www.edx.org",
    "khan academy": "https://www.khanacademy.org",
    "freecodecamp": "https://www.freecodecamp.org",
    "codecademy": "https://www.codecademy.com",
    "udacity": "https://www.udacity.com",
    "pluralsight": "https://www.pluralsight.com",
    "mit": "https://ocw.mit.edu",
    "harvard": "https://pll.harvard.edu",
    "youtube": "https://www.youtube.com",
    "github": "https://www.github.com",
    "python": "https://www.python.org",
    "flutter": "https://flutter.dev",
    "react": "https://react.dev"
}


@dataclass
class ResolutionResult:
    handled: bool
    response: str
    ambiguous: bool = False
    entity: Optional[str] = None
    url: Optional[str] = None


class ReferenceResolver:
    """
    Deterministically resolves follow-up questions from recent conversation turns.
    Prevents 60s local model inference timeouts for deterministic link and reference queries.
    """

    @classmethod
    def resolve(cls, message: str, history: List[Dict[str, Any]]) -> Optional[ResolutionResult]:
        """
        Evaluate if a message is a contextual follow-up that can be resolved deterministically.
        :param message: Current user query.
        :param history: Recent conversation turns (each containing role and message / content).
        :return: ResolutionResult if resolved, or None if LLM reasoning is required.
        """
        clean = message.strip().lower()
        if not clean:
            return None

        # 1. Check for link / URL follow-up request patterns
        is_link_request = bool(re.search(
            r"\b(?:provide|give\s+me|send\s+me|get|what\s+is|what's|where\s+is|open)\s+(?:the|that|my)?\s*([a-zA-Z0-9_\-\s]+)?\s*(?:link|url|website)\b",
            clean
        ) or re.search(r"^(?:link|url|website)\s*(?:please)?$", clean))

        # 2. Check for recommendation recall patterns
        is_recom_recall = bool(re.search(
            r"\b(?:what\s+(?:course|courses|book|books|item|items|options?)\s+did\s+you\s+recommend|"
            r"which\s+(?:course|courses|book|options?)\s+did\s+you\s+mention|"
            r"what\s+was\s+(?:that|the)\s+(?:course|recommendation))\b",
            clean
        ))

        if not is_link_request and not is_recom_recall:
            return None

        # Inspect recent assistant turns (up to 4 turns back)
        assistant_turns = [
            t.get("assistant_response") or t.get("message") or t.get("content") or ""
            for t in reversed(history)
            if t.get("role") in ("assistant", "tony") or "assistant_response" in t
        ][:4]

        recent_context = "\n".join(assistant_turns)
        if not recent_context.strip():
            if is_link_request:
                return ResolutionResult(
                    handled=True,
                    response="I don't see any links or courses mentioned in our recent conversation, Sir."
                )
            return None

        # -------------------------------------------------------------
        # Branch A: Recommendation Recall ("what course did you recommend?")
        # -------------------------------------------------------------
        if is_recom_recall:
            courses_found = cls._extract_quoted_courses(recent_context)
            if courses_found:
                items_str = ", ".join([f"'{c}'" for c in courses_found])
                return ResolutionResult(
                    handled=True,
                    response=f"In our earlier discussion, I recommended: {items_str}, Sir.",
                    entity=items_str
                )
            return ResolutionResult(
                handled=True,
                response="Looking at our recent conversation, we discussed learning options, but no specific course titles were recorded, Sir."
            )

        # -------------------------------------------------------------
        # Branch B: Link / URL Follow-Up ("provide the coursera link")
        # -------------------------------------------------------------
        # Extract explicit platform/service keyword if specified by user
        target_entity = None
        link_target_match = re.search(
            r"\b(?:provide|give\s+me|send\s+me|get|open)\s+(?:the|that|my)?\s*([a-zA-Z0-9_\-]+)\s+(?:link|url|website)\b",
            clean
        )
        if link_target_match:
            candidate = link_target_match.group(1).strip().lower()
            if candidate not in ("course", "learning", "study", "the", "that", "this", "a", "an"):
                target_entity = candidate

        # Collect URLs present in recent assistant context
        urls_in_context = re.findall(r"https?://[^\s)\]\"'>]+", recent_context)

        # Detect platforms mentioned in recent context
        platforms_in_context = []
        for p in COMMON_PLATFORMS:
            if re.search(rf"\b{re.escape(p)}\b", recent_context, re.IGNORECASE):
                platforms_in_context.append(p)

        courses_in_context = cls._extract_quoted_courses(recent_context)

        # Case 1: Specific entity requested (e.g. "Coursera", "Udemy", "Python")
        if target_entity:
            # Check if mentioned in previous context
            mentioned = bool(
                re.search(rf"\b{re.escape(target_entity)}\b", recent_context, re.IGNORECASE) or
                target_entity in COMMON_PLATFORMS
            )

            # Check for direct URL in context matching target
            matching_url = next((u for u in urls_in_context if target_entity in u.lower()), None)
            if matching_url:
                return ResolutionResult(
                    handled=True,
                    response=f"Here is the {target_entity.title()} link from our earlier discussion, Sir: {matching_url}",
                    entity=target_entity,
                    url=matching_url
                )

            # If platform is known (e.g. Coursera), provide its verified root URL
            canonical_url = COMMON_PLATFORMS.get(target_entity) or KNOWN_SERVICES.get(target_entity)
            if canonical_url:
                if mentioned:
                    return ResolutionResult(
                        handled=True,
                        response=(
                            f"Here is the {target_entity.title()} link, Sir: {canonical_url}\n"
                            f"While we discussed {target_entity.title()} in our recommendations, I do not have a direct course deep-link stored in memory."
                        ),
                        entity=target_entity,
                        url=canonical_url
                    )
                else:
                    return ResolutionResult(
                        handled=True,
                        response=f"We haven't discussed {target_entity.title()} recently, but you can access it here, Sir: {canonical_url}",
                        entity=target_entity,
                        url=canonical_url
                    )

            # Target entity not known and not in context
            return ResolutionResult(
                handled=True,
                response=f"I don't have a verified link available for '{target_entity.title()}', Sir.",
                entity=target_entity
            )

        # Case 2: Unspecified link requested (e.g. "provide the link", "give me the URL")
        # Check if multiple platforms or multiple courses were discussed -> AMBIGUOUS
        all_options = list(dict.fromkeys(platforms_in_context + courses_in_context))
        if len(all_options) > 1:
            opts_desc = " and ".join([f"'{opt.title()}'" for opt in all_options[:3]])
            return ResolutionResult(
                handled=True,
                ambiguous=True,
                response=f"We discussed multiple options ({opts_desc}), Sir. Which specific link would you like me to provide?"
            )

        # If exactly one platform mentioned
        if len(platforms_in_context) == 1:
            p = platforms_in_context[0]
            p_url = COMMON_PLATFORMS.get(p, f"https://www.{p}.com")
            return ResolutionResult(
                handled=True,
                response=f"Here is the link for {p.title()}, Sir: {p_url}",
                entity=p,
                url=p_url
            )

        # If explicit URLs exist in recent context
        if urls_in_context:
            return ResolutionResult(
                handled=True,
                response=f"Here is the link from our earlier conversation, Sir: {urls_in_context[0]}",
                url=urls_in_context[0]
            )

        # No links found in recent context
        return ResolutionResult(
            handled=True,
            response="I don't have a specific link saved from our previous conversation, Sir. Could you specify which course or platform you need?"
        )

    @staticmethod
    def _extract_quoted_courses(text: str) -> List[str]:
        """Extract course or book titles enclosed in single/double quotes or bullets."""
        quoted = re.findall(r"['\"]([A-Z0-9][^'\"\n]{3,60})['\"]", text)
        filtered = [
            q.strip() for q in quoted
            if not any(k in q.lower() for k in ("sir", "tony", "completed", "error", "failed", "step", "http"))
        ]
        return list(dict.fromkeys(filtered))
