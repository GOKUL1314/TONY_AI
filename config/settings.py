"""
Application settings and configuration management for TONY.
Loads settings from environment variables and provides structured access.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if present
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
else:
    load_dotenv(override=True)


class Config:
    """Application configuration container."""

    # Project directories
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    CONVERSATIONS_DIR: Path = DATA_DIR / "conversations"
    AUDIO_DIR: Path = DATA_DIR / "audio"
    IMAGE_DIR: Path = DATA_DIR / "generated_images"
    IMAGE_HISTORY_FILE: Path = DATA_DIR / "image_history.json"
    LOGS_DIR: Path = BASE_DIR / "logs"

    # AI Configuration (Stage 1)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "local").lower().strip()
    AI_MODEL: str = os.getenv("AI_MODEL", "llama3.2:1b").strip()

    # Local LLM (Ollama) Settings
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "120"))

    # Cloud API Settings
    API_KEY: str = os.getenv("API_KEY", "").strip()
    API_BASE_URL: str = os.getenv("API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    API_TIMEOUT: int = int(os.getenv("API_TIMEOUT", "45"))

    # Voice Configuration (Stage 2)
    STT_PROVIDER: str = os.getenv("STT_PROVIDER", "whisper").lower().strip()
    STT_MODEL: str = os.getenv("STT_MODEL", "tiny").strip()
    STT_DEVICE: str = os.getenv("STT_DEVICE", "cpu").strip()
    STT_COMPUTE_TYPE: str = os.getenv("STT_COMPUTE_TYPE", "int8").strip()

    TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "local").lower().strip()
    TTS_VOICE: str = os.getenv("TTS_VOICE", "default").strip()
    TTS_RATE: int = int(os.getenv("TTS_RATE", "175"))

    # Continuous Conversation & Hands-Free Settings (Stage 3)
    CONTINUOUS_MODE: bool = os.getenv("CONTINUOUS_MODE", "true").lower() in ("true", "1", "yes")
    WAKE_WORD_ENABLED: bool = os.getenv("WAKE_WORD_ENABLED", "true").lower() in ("true", "1", "yes")
    WAKE_WORD: str = os.getenv("WAKE_WORD", "tony").lower().strip()
    WAKE_WORD_CONFIDENCE: float = float(os.getenv("WAKE_WORD_CONFIDENCE", "0.65"))
    WAKE_WORD_COOLDOWN_MS: int = int(os.getenv("WAKE_WORD_COOLDOWN_MS", "1500"))
    VOICE_SILENCE_TIMEOUT: float = float(os.getenv("VOICE_SILENCE_TIMEOUT", "1.2"))
    MICROPHONE_ENABLED: bool = os.getenv("MICROPHONE_ENABLED", "true").lower() in ("true", "1", "yes")
    AUDIO_DUCKING: bool = os.getenv("AUDIO_DUCKING", "true").lower() in ("true", "1", "yes")

    # Long-Term Memory & Context Settings (Stage 4)
    MEMORY_ENABLED: bool = os.getenv("MEMORY_ENABLED", "true").lower() in ("true", "1", "yes")
    MEMORY_DATABASE: Path = Path(os.getenv("MEMORY_DATABASE", str(DATA_DIR / "memory.db")))
    MEMORY_AUTO_SAVE: bool = os.getenv("MEMORY_AUTO_SAVE", "true").lower() in ("true", "1", "yes")
    MEMORY_SEMANTIC_SEARCH: bool = os.getenv("MEMORY_SEMANTIC_SEARCH", "false").lower() in ("true", "1", "yes")
    MEMORY_MAX_RESULTS: int = int(os.getenv("MEMORY_MAX_RESULTS", "5"))
    MEMORY_MIN_RELEVANCE: float = float(os.getenv("MEMORY_MIN_RELEVANCE", "0.15"))

    # Tool Execution & Safe Windows Automation Settings (Stage 5)
    TOOLS_ENABLED: bool = os.getenv("TOOLS_ENABLED", "true").lower() in ("true", "1", "yes")
    TOOL_CONFIRMATION_ENABLED: bool = os.getenv("TOOL_CONFIRMATION_ENABLED", "true").lower() in ("true", "1", "yes")
    TOOL_CONFIRMATION_TIMEOUT: int = int(os.getenv("TOOL_CONFIRMATION_TIMEOUT", "60"))
    TOOL_MAX_SEARCH_RESULTS: int = int(os.getenv("TOOL_MAX_SEARCH_RESULTS", "20"))
    TOOLS_ALLOW_FILE_OPERATIONS: bool = os.getenv("TOOLS_ALLOW_FILE_OPERATIONS", "true").lower() in ("true", "1", "yes")
    TOOLS_ALLOW_APPLICATIONS: bool = os.getenv("TOOLS_ALLOW_APPLICATIONS", "true").lower() in ("true", "1", "yes")
    TOOLS_ALLOW_BROWSER: bool = os.getenv("TOOLS_ALLOW_BROWSER", "true").lower() in ("true", "1", "yes")
    TOOLS_ALLOW_VOLUME: bool = os.getenv("TOOLS_ALLOW_VOLUME", "true").lower() in ("true", "1", "yes")
    TOOLS_ALLOW_MEDIA: bool = os.getenv("TOOLS_ALLOW_MEDIA", "true").lower() in ("true", "1", "yes")

    # Image Generation Settings (Stage 6)
    IMAGE_PROVIDER: str = os.getenv("IMAGE_PROVIDER", "pollinations").lower().strip()
    IMAGE_MODEL: str = os.getenv("IMAGE_MODEL", "sana").strip()
    POLLINATIONS_API_BASE_URL: str = os.getenv("POLLINATIONS_API_BASE_URL", "https://image.pollinations.ai").rstrip("/")
    IMAGE_API_KEY: str = os.getenv("IMAGE_API_KEY", "").strip()
    IMAGE_API_BASE_URL: str = os.getenv("IMAGE_API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    IMAGE_DEFAULT_WIDTH: int = int(os.getenv("IMAGE_DEFAULT_WIDTH", "1024"))
    IMAGE_DEFAULT_HEIGHT: int = int(os.getenv("IMAGE_DEFAULT_HEIGHT", "1024"))
    IMAGE_MAX_HISTORY: int = int(os.getenv("IMAGE_MAX_HISTORY", "100"))
    IMAGE_TIMEOUT: int = int(os.getenv("IMAGE_TIMEOUT", "60"))
    IMAGE_PROMPT_ENHANCEMENT: bool = os.getenv("IMAGE_PROMPT_ENHANCEMENT", "true").lower() in ("true", "1", "yes")

    # Video Generation Settings (Stage 7)
    VIDEO_PROVIDER: str = os.getenv("VIDEO_PROVIDER", "huggingface").lower().strip()
    VIDEO_ALLOW_PAID: bool = os.getenv("VIDEO_ALLOW_PAID", "false").lower() in ("true", "1", "yes")
    HF_TOKEN: str = os.getenv("HF_TOKEN", "").strip()
    HF_VIDEO_PROVIDER: str = os.getenv("HF_VIDEO_PROVIDER", os.getenv("HF_PROVIDER", "wavespeed")).strip()
    HF_VIDEO_MODEL: str = os.getenv("HF_VIDEO_MODEL", "Wan-AI/Wan2.1-T2V-14B").strip()

    VIDEO_LOCAL_MODEL: str = os.getenv("VIDEO_LOCAL_MODEL", "").strip()
    VIDEO_LOCAL_MODEL_PATH: str = os.getenv("VIDEO_LOCAL_MODEL_PATH", "").strip()
    VIDEO_LOCAL_DEVICE: str = os.getenv("VIDEO_LOCAL_DEVICE", "auto").lower().strip()

    VIDEO_DEFAULT_DURATION: int = int(os.getenv("VIDEO_DEFAULT_DURATION", "5"))
    VIDEO_MAX_DURATION: int = int(os.getenv("VIDEO_MAX_DURATION", "5"))
    VIDEO_DEFAULT_WIDTH: int = int(os.getenv("VIDEO_DEFAULT_WIDTH", "512"))
    VIDEO_DEFAULT_HEIGHT: int = int(os.getenv("VIDEO_DEFAULT_HEIGHT", "512"))
    VIDEO_DEFAULT_FPS: int = int(os.getenv("VIDEO_DEFAULT_FPS", "16"))
    VIDEO_MAX_FILE_SIZE_MB: int = int(os.getenv("VIDEO_MAX_FILE_SIZE_MB", "200"))
    VIDEO_TIMEOUT: int = int(os.getenv("VIDEO_TIMEOUT", "300"))
    VIDEO_MAX_HISTORY: int = int(os.getenv("VIDEO_MAX_HISTORY", "100"))
    VIDEO_MAX_CONCURRENT_JOBS: int = int(os.getenv("VIDEO_MAX_CONCURRENT_JOBS", "1"))
    VIDEO_PROMPT_ENHANCEMENT: bool = os.getenv("VIDEO_PROMPT_ENHANCEMENT", "true").lower() in ("true", "1", "yes")
    RUN_REAL_VIDEO_TEST: bool = os.getenv("RUN_REAL_VIDEO_TEST", "false").lower() in ("true", "1", "yes")

    VIDEO_DIR: Path = DATA_DIR / "generated_videos"
    VIDEO_THUMBNAILS_DIR: Path = DATA_DIR / "generated_videos" / "thumbnails"
    VIDEO_HISTORY_FILE: Path = DATA_DIR / "video_history.json"

    # Vision & Image Understanding Settings (Stage 9)
    VISION_PROVIDER: str = os.getenv("VISION_PROVIDER", "ollama").lower().strip()
    VISION_MODEL: str = os.getenv("VISION_MODEL", "moondream").strip()
    VISION_MAX_FILE_SIZE_MB: int = int(os.getenv("VISION_MAX_FILE_SIZE_MB", "10"))
    VISION_TIMEOUT: int = int(os.getenv("VISION_TIMEOUT", "90"))
    VISION_MAX_HISTORY: int = int(os.getenv("VISION_MAX_HISTORY", "100"))
    VISION_DIR: Path = DATA_DIR / "uploaded_images"
    VISION_HISTORY_FILE: Path = DATA_DIR / "vision_history.json"

    # Personal Knowledge & RAG System Settings (Stage 11)
    KNOWLEDGE_ENABLED: bool = os.getenv("KNOWLEDGE_ENABLED", "true").lower() in ("true", "1", "yes")
    KNOWLEDGE_EMBEDDING_PROVIDER: str = os.getenv("KNOWLEDGE_EMBEDDING_PROVIDER", "ollama").lower().strip()
    KNOWLEDGE_EMBEDDING_MODEL: str = os.getenv("KNOWLEDGE_EMBEDDING_MODEL", "nomic-embed-text").strip()
    KNOWLEDGE_CHUNK_SIZE: int = int(os.getenv("KNOWLEDGE_CHUNK_SIZE", "800"))
    KNOWLEDGE_CHUNK_OVERLAP: int = int(os.getenv("KNOWLEDGE_CHUNK_OVERLAP", "150"))
    KNOWLEDGE_TOP_K: int = int(os.getenv("KNOWLEDGE_TOP_K", "5"))
    KNOWLEDGE_MAX_FILE_SIZE_MB: int = int(os.getenv("KNOWLEDGE_MAX_FILE_SIZE_MB", "25"))
    KNOWLEDGE_STORAGE_DIR: Path = DATA_DIR / "knowledge"
    KNOWLEDGE_SEMANTIC_WEIGHT: float = float(os.getenv("KNOWLEDGE_SEMANTIC_WEIGHT", "0.65"))
    KNOWLEDGE_KEYWORD_WEIGHT: float = float(os.getenv("KNOWLEDGE_KEYWORD_WEIGHT", "0.35"))

    # Personalization & Proactive Intelligence Settings (Stage 12)
    PERSONALIZATION_ENABLED: bool = os.getenv("PERSONALIZATION_ENABLED", "true").lower() in ("true", "1", "yes")
    PERSONALIZATION_STORAGE_DIR: Path = DATA_DIR / "personalization"
    PERSONALIZATION_DATABASE: Path = Path(os.getenv("PERSONALIZATION_DATABASE", str(DATA_DIR / "personalization" / "personalization.db")))
    PROACTIVE_ENABLED: bool = os.getenv("PROACTIVE_ENABLED", "false").lower() in ("true", "1", "yes")
    PROACTIVE_DAILY_BRIEFING_ENABLED: bool = os.getenv("PROACTIVE_DAILY_BRIEFING_ENABLED", "false").lower() in ("true", "1", "yes")
    PROACTIVE_EVENING_SUMMARY_ENABLED: bool = os.getenv("PROACTIVE_EVENING_SUMMARY_ENABLED", "false").lower() in ("true", "1", "yes")
    PROACTIVE_QUIET_HOURS_START: str = os.getenv("PROACTIVE_QUIET_HOURS_START", "22:00").strip()
    PROACTIVE_QUIET_HOURS_END: str = os.getenv("PROACTIVE_QUIET_HOURS_END", "07:00").strip()
    PROACTIVE_MAX_NOTIFICATIONS_PER_DAY: int = int(os.getenv("PROACTIVE_MAX_NOTIFICATIONS_PER_DAY", "5"))
    PROACTIVE_TIMEZONE: str = os.getenv("PROACTIVE_TIMEZONE", "Asia/Kolkata").strip()
    PROACTIVE_DAILY_BRIEFING_TIME: str = os.getenv("PROACTIVE_DAILY_BRIEFING_TIME", "08:00").strip()
    PROACTIVE_EVENING_SUMMARY_TIME: str = os.getenv("PROACTIVE_EVENING_SUMMARY_TIME", "21:00").strip()

    # Server Settings
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "5000"))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "tony-ai-secret-key-dev")

    # TONY Persona & System Instructions
    SYSTEM_PROMPT: str = (
        "You are TONY, a calm, intelligent, and helpful personal AI desktop assistant. "
        "Your responses are clear, polite, structured, and insightful. "
        "Maintain a composed and capable tone at all times. "
        "Strictly adhere to your current stage of development: "
        "You are currently in Stage 12 (Advanced Personalization & Proactive Intelligence enabled). "
        "You can converse naturally, adapt to user communication and learning preferences, "
        "manage scheduled reminders, recurring tasks, daily routines, morning briefings, "
        "and proactive suggestions while strictly respecting quiet hours and confirmation safety policies."
    )

    @classmethod
    def ensure_directories(cls):
        """Ensure necessary runtime directories exist."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        cls.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        cls.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        cls.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        cls.VIDEO_THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
        cls.VISION_DIR.mkdir(parents=True, exist_ok=True)
        cls.KNOWLEDGE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        cls.PERSONALIZATION_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)


def get_config() -> type[Config]:
    """Retrieve application configuration with initialized directories."""
    Config.ensure_directories()
    return Config

