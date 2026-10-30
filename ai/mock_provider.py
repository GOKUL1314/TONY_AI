"""
Mock / Offline AI Provider for testing and standalone demonstration.
Produces deterministic, calm responses adhering to TONY's persona without network calls.
Integrates memory context awareness for Stage 4 evaluation.
"""
import logging
import re
from typing import Any
from ai.provider import AIProvider

logger = logging.getLogger("tony.ai.mock")


class MockProvider(AIProvider):
    """
    Offline/Mock provider implementing TONY's persona and memory context awareness.
    Useful for automated testing and offline UI evaluation.
    """

    def __init__(self, model_name: str = "tony-mock-v1", system_prompt: str = ""):
        super().__init__(model_name=model_name)
        self.system_prompt = system_prompt
        self.provider_name = "mock (offline)"

    def generate_response(self, message: str, history: list[dict[str, str]] | None = None) -> str:
        """
        Generate a calm, intelligent mock response tailored to TONY's persona and memory context.
        """
        clean = message.strip().lower()

        # Check for memory context injected into history
        memory_context = ""
        if history:
            for turn in history:
                if turn.get("role") == "system" and "RELEVANT USER MEMORY:" in turn.get("message", ""):
                    memory_context = turn.get("message", "")
                    break

        # 1. Answer memory queries from context if available
        if memory_context:
            if "name" in clean or "who am i" in clean:
                name_match = re.search(r"(?i)- Name:\s*([^\n]+)", memory_context)
                if name_match:
                    return f"Your name is {name_match.group(1).strip()}."

            if "language" in clean or "programming" in clean or "code" in clean:
                lang_match = re.search(r"(?i)- (?:Language|Preferred Programming Language|Language Preference):\s*([^\n]+)", memory_context)
                if lang_match:
                    return f"You use {lang_match.group(1).strip()}."

            if "learning" in clean or "learn" in clean:
                learn_match = re.search(r"(?i)- (?:Learning|Learning Topic|Learning Skill):\s*([^\n]+)", memory_context)
                if learn_match:
                    return f"You are learning {learn_match.group(1).strip()}."

            if "project" in clean:
                proj_match = re.search(r"(?i)- (?:Project|Project Name):\s*([^\n]+)", memory_context)
                if proj_match:
                    return f"Your project is {proj_match.group(1).strip()}."

        # 2. Standard TONY Stage 1-4 Persona Greetings and Capabilities
        if any(greet in clean for greet in ["hello", "hi tony", "hey tony", "good morning", "good evening", "good afternoon"]):
            return "Good evening. I'm Tony. How can I assist you?"

        if "what can you do" in clean or "capabilities" in clean or "features" in clean:
            return (
                "I can help you with questions, coding, research, planning, files, and many other tasks. "
                "We'll gradually give me more capabilities."
            )

        if "who are you" in clean or "what is tony" in clean:
            return (
                "I am TONY, your personal AI desktop assistant. "
                "We are currently in Stage 5 of my development, with long-term memory and safe Windows system automation active."
            )

        if "stage" in clean or "roadmap" in clean:
            return (
                "We are currently executing Stage 5: Tool Execution & Safe Windows System Automation. "
                "Stages 1, 2, 3, and 4 established conversational foundations, voice I/O, hands-free conversation, and long-term memory."
            )

        if "status" in clean or "system" in clean:
            return "All internal subsystems for Stage 5 are nominal and operational."

        # Research and planning simulation for offline testing
        task_clean = clean
        if "current task:" in clean:
            task_clean = clean.split("current task:", 1)[1].split("\n")[0].strip()

        if "research" in task_clean or ("python" in task_clean and "course" in task_clean):
            return (
                "Live web search is currently unavailable in this environment. Based on internal knowledge, the top recommended Python courses are 'Python Crash Course' by Eric Matthes and '100 Days of Code: The Complete Python Pro Bootcamp' by Dr. Angela Yu. Please note that live ratings and course availability should be verified directly on their respective platforms."
            )

        if "plan" in task_clean or "schedule" in task_clean:
            return (
                "Here is your structured Python learning plan:\n- Week 1: Core Syntax & Data Structures\n- Week 2: Functions & Object-Oriented Programming\n- Week 3: Practical Libraries & Automation\n- Week 4: Capstone Project & Testing."
            )

        if "python course" in clean or ("python" in clean and "course" in clean):
            if "plan" in clean or "schedule" in clean:
                return (
                    "Live web search is currently unavailable in this environment. Based on internal knowledge, the top recommended Python courses are 'Python Crash Course' by Eric Matthes and '100 Days of Code: The Complete Python Pro Bootcamp'. "
                    "Here is a recommended 4-week learning plan: Week 1: Python Basics & Syntax, Week 2: Data Structures & OOP, Week 3: APIs & Automation, Week 4: Capstone Project. Note that course ratings and pricing may change."
                )
            return (
                "Live web search is currently unavailable in this environment. Based on internal knowledge, the top recommended Python courses are 'Python Crash Course' by Eric Matthes and '100 Days of Code: The Complete Python Pro Bootcamp' by Dr. Angela Yu. Please note that live ratings and current availability should be verified directly on their respective platforms."
            )

        if "learning plan" in clean or "study plan" in clean or "learning schedule" in clean:
            return (
                "Here is your structured Python learning plan:\n- Week 1: Core Syntax & Data Structures\n- Week 2: Functions & Object-Oriented Programming\n- Week 3: Practical Libraries & Automation\n- Week 4: Capstone Project & Testing."
            )

        return (
            f"Understood. Regarding '{message.strip()}', I have registered your message. "
            "My Stage 5 reasoning and automation engine is operating smoothly. How would you like to proceed?"
        )

    def check_health(self) -> dict[str, Any]:
        """Mock provider is always available."""
        return {
            "available": True,
            "provider": self.provider_name,
            "model": self.model_name,
            "details": "Mock provider active. Ready for local testing."
        }
