"""Routes package for TONY API."""
from routes.chat import chat_bp
from routes.voice import voice_bp
from routes.memory import memory_bp
from routes.tools import tools_bp

__all__ = ["chat_bp", "voice_bp", "memory_bp", "tools_bp"]
