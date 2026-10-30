"""
Main application entry point for TONY AI Assistant.
Initializes logging, configuration, memory, services, voice subsystems, routes, and Flask server.
"""
import logging
import sys
from pathlib import Path
from flask import Flask, render_template, jsonify
from config.settings import get_config
from ai.provider import get_ai_provider
from services.conversation import ConversationService
from voice.stt_provider import get_stt_provider
from voice.tts_provider import get_tts_provider
from memory.database import MemoryDatabase
from memory.manager import MemoryManager
from memory.extractor import MemoryExtractor
from memory.retriever import get_memory_retriever
from routes.chat import chat_bp
from routes.voice import voice_bp
from routes.memory import memory_bp
from routes.tools import tools_bp
from routes.images import images_bp
from routes.videos import videos_bp
from routes.assistant import assistant_bp
from routes.vision import vision_bp
from routes.agent import agent_bp
from routes.knowledge import knowledge_bp
from routes.personalization import personalization_bp
from routes.self_upgrade import self_upgrade_bp
from knowledge import KnowledgeManager, get_embedding_provider
from personalization import PersonalizationManager
from self_upgrade import SelfUpgradeManager
from agent import AgentPlanner, AgentExecutor, AgentManager
from intelligence import TonyOrchestrator, IntelligencePipeline
from tools import create_default_registry, ConfirmationManager, ToolExecutor, ToolPlanner
from image_generation import (
    ImageStorage,
    ImageHistoryManager,
    get_image_provider,
    ImageGenerationManager
)
from video_generation import (
    VideoStorage,
    VideoHistoryManager,
    VideoJobManager,
    get_video_provider,
    VideoGenerationManager
)
from vision import (
    VisionStorage,
    VisionHistoryManager,
    get_vision_provider,
    VisionManager
)



def setup_logging(logs_dir: Path, debug: bool = False) -> None:
    """Configure structured logging for TONY."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "tony.log"

    log_level = logging.DEBUG if debug else logging.INFO
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    root_logger = logging.getLogger("tony")
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers on reload
    if not root_logger.handlers:
        # File handler
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        root_logger.addHandler(console_handler)


def create_app(config_class=None) -> Flask:
    """
    Application factory for TONY AI.

    :param config_class: Optional configuration class override (useful for testing).
    :return: Configured Flask application instance.
    """
    app = Flask(__name__)

    # Load configuration
    cfg = config_class if config_class else get_config()
    app.config.from_object(cfg)

    # Setup logging
    setup_logging(cfg.LOGS_DIR, debug=cfg.DEBUG)
    logger = logging.getLogger("tony.app")
    logger.info("Initializing TONY AI Assistant (Stage 6: Image Generation Enabled)...")

    # Initialize Core Services (Stage 1)
    conversation_service = ConversationService(storage_dir=cfg.CONVERSATIONS_DIR)
    ai_provider = get_ai_provider(cfg)

    # Initialize Voice Subsystems (Stage 2 & Stage 3)
    stt_provider = get_stt_provider(cfg)
    tts_provider = get_tts_provider(cfg)

    # Initialize Long-Term Memory Subsystem (Stage 4)
    memory_db = MemoryDatabase(db_path=cfg.MEMORY_DATABASE)
    memory_manager = MemoryManager(db=memory_db)
    memory_extractor = MemoryExtractor()
    memory_retriever = get_memory_retriever(manager=memory_manager, config=cfg)

    # Initialize Tool Subsystem (Stage 5)
    tool_registry = create_default_registry()
    tool_confirmation = ConfirmationManager(default_timeout=getattr(cfg, "TOOL_CONFIRMATION_TIMEOUT", 60))
    tool_executor = ToolExecutor(registry=tool_registry, confirmation_manager=tool_confirmation)
    tool_planner = ToolPlanner(registry=tool_registry)

    # Initialize Image Generation Subsystem (Stage 6)
    image_storage = ImageStorage(storage_dir=cfg.IMAGE_DIR)
    image_history = ImageHistoryManager(
        history_file=cfg.IMAGE_HISTORY_FILE,
        max_records=getattr(cfg, "IMAGE_MAX_HISTORY", 100)
    )
    image_provider = get_image_provider(cfg)
    image_manager = ImageGenerationManager(
        provider=image_provider,
        storage=image_storage,
        history=image_history,
        enhance_prompts=getattr(cfg, "IMAGE_PROMPT_ENHANCEMENT", True)
    )

    # Initialize Video Generation Subsystem (Stage 7)
    video_storage = VideoStorage(
        storage_dir=cfg.VIDEO_DIR,
        thumbnails_dir=cfg.VIDEO_THUMBNAILS_DIR
    )
    video_history = VideoHistoryManager(
        history_file=cfg.VIDEO_HISTORY_FILE,
        max_records=getattr(cfg, "VIDEO_MAX_HISTORY", 100)
    )
    video_provider = get_video_provider(cfg)
    video_job_manager = VideoJobManager(
        provider=video_provider,
        storage=video_storage,
        history=video_history,
        max_concurrent_jobs=getattr(cfg, "VIDEO_MAX_CONCURRENT_JOBS", 1)
    )
    video_manager = VideoGenerationManager(
        provider=video_provider,
        storage=video_storage,
        history=video_history,
        job_manager=video_job_manager,
        image_manager=image_manager,
        enhance_prompts=getattr(cfg, "VIDEO_PROMPT_ENHANCEMENT", True),
        default_duration=getattr(cfg, "VIDEO_DEFAULT_DURATION", 5),
        max_duration=getattr(cfg, "VIDEO_MAX_DURATION", 5),
        default_width=getattr(cfg, "VIDEO_DEFAULT_WIDTH", 512),
        default_height=getattr(cfg, "VIDEO_DEFAULT_HEIGHT", 512),
        default_fps=getattr(cfg, "VIDEO_DEFAULT_FPS", 16),
        allow_paid=getattr(cfg, "VIDEO_ALLOW_PAID", False)
    )

    app.config["AI_PROVIDER_INSTANCE"] = ai_provider
    app.config["CONVERSATION_SERVICE_INSTANCE"] = conversation_service
    app.config["STT_PROVIDER_INSTANCE"] = stt_provider
    app.config["TTS_PROVIDER_INSTANCE"] = tts_provider
    app.config["AUDIO_DIR"] = cfg.AUDIO_DIR

    app.config["MEMORY_DATABASE_INSTANCE"] = memory_db
    app.config["MEMORY_MANAGER_INSTANCE"] = memory_manager
    app.config["MEMORY_EXTRACTOR_INSTANCE"] = memory_extractor
    app.config["MEMORY_RETRIEVER_INSTANCE"] = memory_retriever

    app.config["TOOL_REGISTRY_INSTANCE"] = tool_registry
    app.config["TOOL_CONFIRMATION_INSTANCE"] = tool_confirmation
    app.config["TOOL_EXECUTOR_INSTANCE"] = tool_executor
    app.config["TOOL_PLANNER_INSTANCE"] = tool_planner

    app.config["IMAGE_STORAGE_INSTANCE"] = image_storage
    app.config["IMAGE_HISTORY_INSTANCE"] = image_history
    app.config["IMAGE_PROVIDER_INSTANCE"] = image_provider
    app.config["IMAGE_MANAGER_INSTANCE"] = image_manager

    app.config["VIDEO_STORAGE_INSTANCE"] = video_storage
    app.config["VIDEO_HISTORY_INSTANCE"] = video_history
    app.config["VIDEO_PROVIDER_INSTANCE"] = video_provider
    app.config["VIDEO_JOB_MANAGER_INSTANCE"] = video_job_manager
    app.config["VIDEO_MANAGER_INSTANCE"] = video_manager

    # Initialize Vision Subsystem (Stage 9)
    vision_storage = VisionStorage(
        storage_dir=cfg.VISION_DIR,
        max_size_mb=getattr(cfg, "VISION_MAX_FILE_SIZE_MB", 10)
    )
    vision_history = VisionHistoryManager(
        history_file=cfg.VISION_HISTORY_FILE,
        max_records=getattr(cfg, "VISION_MAX_HISTORY", 100)
    )
    vision_provider = get_vision_provider(cfg)
    vision_manager = VisionManager(
        provider=vision_provider,
        storage=vision_storage,
        history=vision_history,
        image_manager=image_manager
    )

    app.config["VISION_STORAGE_INSTANCE"] = vision_storage
    app.config["VISION_HISTORY_INSTANCE"] = vision_history
    app.config["VISION_PROVIDER_INSTANCE"] = vision_provider
    app.config["VISION_MANAGER_INSTANCE"] = vision_manager

    # Initialize Intelligence & Orchestration Subsystem (Stage 8)
    orchestrator = TonyOrchestrator(
        ai_provider=ai_provider,
        conversation_service=conversation_service,
        memory_manager=memory_manager,
        memory_retriever=memory_retriever,
        memory_extractor=memory_extractor,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
        tool_confirmation=tool_confirmation,
        image_manager=image_manager,
        video_manager=video_manager,
        vision_manager=vision_manager,
        stt_provider=stt_provider,
        tts_provider=tts_provider,
        max_step_retries=getattr(cfg, "MAX_STEP_RETRIES", 2)
    )
    app.config["ORCHESTRATOR_INSTANCE"] = orchestrator

    # Initialize Personal Knowledge & RAG Subsystem (Stage 11)
    embedding_provider = get_embedding_provider(cfg)
    knowledge_manager = KnowledgeManager(
        storage_dir=cfg.KNOWLEDGE_STORAGE_DIR,
        embedding_provider=embedding_provider,
        ai_provider=ai_provider,
        max_file_size_mb=getattr(cfg, "KNOWLEDGE_MAX_FILE_SIZE_MB", 25)
    )
    app.config["KNOWLEDGE_MANAGER_INSTANCE"] = knowledge_manager

    # Initialize Personalization & Proactive Intelligence Subsystem (Stage 12)
    personalization_manager = PersonalizationManager(
        storage_dir=getattr(cfg, "PERSONALIZATION_STORAGE_DIR", cfg.DATA_DIR / "personalization"),
        tts_provider=tts_provider,
        ai_provider=ai_provider,
        default_timezone=getattr(cfg, "PROACTIVE_TIMEZONE", "Asia/Kolkata"),
        proactive_enabled=getattr(cfg, "PROACTIVE_ENABLED", False)
    )
    app.config["PERSONALIZATION_MANAGER_INSTANCE"] = personalization_manager
    if getattr(cfg, "PERSONALIZATION_ENABLED", True):
        personalization_manager.start_scheduler()

    # Initialize Agent Subsystem (Stage 10)
    agent_planner = AgentPlanner(tool_registry=tool_registry)
    agent_executor = AgentExecutor(
        tool_executor=tool_executor,
        image_manager=image_manager,
        video_manager=video_manager,
        vision_manager=vision_manager,
        memory_manager=memory_manager,
        memory_retriever=memory_retriever,
        ai_provider=ai_provider,
        confirmation_manager=tool_confirmation,
        knowledge_manager=knowledge_manager,
        personalization_manager=personalization_manager
    )
    agent_manager = AgentManager(
        planner=agent_planner,
        executor=agent_executor,
        orchestrator=orchestrator
    )
    app.config["AGENT_PLANNER_INSTANCE"] = agent_planner
    app.config["AGENT_EXECUTOR_INSTANCE"] = agent_executor
    app.config["AGENT_MANAGER_INSTANCE"] = agent_manager

    # Initialize Self-Upgrade Subsystem
    self_upgrade_manager = SelfUpgradeManager(
        project_root=cfg.BASE_DIR,
        data_dir=cfg.DATA_DIR,
        app_context=app
    )
    app.config["SELF_UPGRADE_MANAGER_INSTANCE"] = self_upgrade_manager

    # Initialize Intelligence Pipeline
    intelligence_pipeline = IntelligencePipeline(
        ai_provider=ai_provider,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
        memory_manager=memory_manager,
        memory_retriever=memory_retriever,
        knowledge_manager=knowledge_manager,
        personalization_manager=personalization_manager,
        app_context=app
    )
    app.config["INTELLIGENCE_PIPELINE_INSTANCE"] = intelligence_pipeline

    # Register Blueprints
    app.register_blueprint(chat_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(memory_bp)
    app.register_blueprint(tools_bp)
    app.register_blueprint(images_bp)
    app.register_blueprint(videos_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(vision_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(personalization_bp)
    app.register_blueprint(self_upgrade_bp)

    # UI Route
    @app.route("/")
    def index():
        stats = memory_manager.get_stats()
        k_stats = knowledge_manager.get_stats()
        p_stats = personalization_manager.get_stats()
        p_status = personalization_manager.get_proactive_status()
        return render_template(
            "index.html",
            provider_name=ai_provider.provider_name,
            model_name=ai_provider.model_name,
            stt_provider=stt_provider.provider_name,
            tts_provider=tts_provider.provider_name,
            memory_count=stats.get("active_memories", 0),
            tool_count=tool_registry.count(),
            image_count=image_history.count(),
            video_count=video_history.count(),
            vision_provider=vision_provider.provider_name,
            vision_model=vision_provider.model_name,
            doc_count=k_stats.get("total_documents", 0),
            reminder_count=p_stats.get("reminders_active", 0),
            proactive_enabled=p_status.get("proactive_mode", False)
        )


    # Global Error Handlers
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal Server Error: {e}")
        return jsonify({"error": "Internal server error"}), 500

    logger.info(
        f"TONY Core ready. AI: {ai_provider.provider_name} | "
        f"Voice: {stt_provider.provider_name}/{tts_provider.provider_name} | "
        f"Memory: {memory_manager.get_stats().get('active_memories', 0)} items active | "
        f"Tools: {tool_registry.count()} tools registered | "
        f"Images: {image_history.count()} images recorded | "
        f"Videos: {video_history.count()} videos recorded"
    )
    return app


app = create_app()

if __name__ == "__main__":
    cfg = get_config()
    tool_reg = app.config.get("TOOL_REGISTRY_INSTANCE")
    tool_cnt = tool_reg.count() if tool_reg else 0
    img_hist = app.config.get("IMAGE_HISTORY_INSTANCE")
    img_cnt = img_hist.count() if img_hist else 0
    vid_hist = app.config.get("VIDEO_HISTORY_INSTANCE")
    vid_cnt = vid_hist.count() if vid_hist else 0
    k_mgr = app.config.get("KNOWLEDGE_MANAGER_INSTANCE")
    k_stats = k_mgr.get_stats() if k_mgr else {}
    doc_cnt = k_stats.get("total_documents", 0)
    pers_mgr = app.config.get("PERSONALIZATION_MANAGER_INSTANCE")
    rem_cnt = len(pers_mgr.scheduler.list_reminders()) if pers_mgr else 0
    proactive_st = "Active" if getattr(cfg, "PROACTIVE_ENABLED", False) else "Standby (Safe)"
    print("=" * 65)
    print("           TONY - Personal AI Desktop Assistant")
    print("   Stage 12: Advanced Personalization & Proactive Intelligence")
    print("=" * 65)
    print(f" -> AI Provider    : {cfg.AI_PROVIDER} ({cfg.AI_MODEL})")
    print(f" -> STT Engine     : {cfg.STT_PROVIDER} ({cfg.STT_MODEL})")
    print(f" -> TTS Engine     : {cfg.TTS_PROVIDER} ({cfg.TTS_VOICE})")
    print(f" -> Memory Engine  : SQLite ({cfg.MEMORY_DATABASE})")
    print(f" -> Tools Engine   : {tool_cnt} registered tools")
    print(f" -> Image Engine   : {cfg.IMAGE_PROVIDER} ({cfg.IMAGE_MODEL}) [{img_cnt} stored]")
    print(f" -> Video Engine   : {cfg.VIDEO_PROVIDER} ({cfg.HF_VIDEO_MODEL}) [{vid_cnt} stored]")
    print(f" -> Knowledge Base : SQLite + FTS5 [{doc_cnt} docs indexed]")
    print(f" -> Personalization: Active (Profile, {rem_cnt} reminders, Proactive: {proactive_st})")
    print(f" -> Orchestrator   : Active (Multi-Step, Context, Security Gated)")
    print(f" -> Access Server  : http://{cfg.HOST}:{cfg.PORT}")
    print("=" * 65)
    app.run(host=cfg.HOST, port=cfg.PORT, debug=cfg.DEBUG)

