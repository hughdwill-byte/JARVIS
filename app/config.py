"""Central configuration.

Loads `.env` (if present) and exposes a single `Config` object.
Every setting has a working default so the app boots with no .env at all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is a convenience, not a hard requirement
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


def _opt_int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def _float(value: str | None, default: float) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except ValueError:
        return default


@dataclass
class Config:
    # LLM
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    llm_model_fast: str = "claude-haiku-4-5"
    llm_model_smart: str = "claude-sonnet-5"
    # Premium tier: only used when the user explicitly asks for heavy work
    # ("in-depth report", "deep dive", "use opus") — never on ordinary chat.
    llm_model_deep: str = "claude-opus-4-8"
    llm_max_tokens: int = 1024

    # Local models via Ollama (LLM_PROVIDER=ollama or local_first).
    # local_first = everyday chat on the free local model, cloud only for
    # hard/deep/vision/agent work — the cheapest and most private setup.
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout_s: int = 120
    # Local embedding model (for RAG: /ask and /index). Runs on the same
    # Ollama server. Install once: `ollama pull nomic-embed-text`.
    embed_model: str = "nomic-embed-text"

    # Markdown/Obsidian vault: where /export writes notes, memories and tasks.
    obsidian_vault: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "vault")

    # Vision
    vision_provider: str = "anthropic"
    camera_index: int = 0
    vision_max_image_edge: int = 1024
    snapshot_retention_days: int = 7

    # STT
    stt_provider: str = "local_whisper"
    whisper_model_size: str = "base"
    mic_device_index: int | None = None
    mic_sample_rate: int = 16000

    # Wake word ("hey jarvis" hands-free mode)
    wake_word_enabled: bool = False
    wake_word_model: str = "hey_jarvis"
    wake_word_threshold: float = 0.5
    # After JARVIS answers, keep listening briefly so you can reply without
    # saying the wake word again.
    follow_up_listen: bool = True
    # Interrupt JARVIS by talking over it (sustained speech cuts it off).
    barge_in: bool = True

    # TTS
    tts_provider: str = "pyttsx3"
    tts_rate: int = 180
    tts_voice: str = ""  # system voice id; "" = OS default (pick in Settings)
    speaker_device_index: int | None = None  # None = system default output
    # Piper: natural, offline neural TTS (TTS_PROVIDER=piper). Needs the piper
    # binary on PATH and a downloaded voice model (.onnx). Falls back to the OS
    # voice if either is missing, so turning it on can never make JARVIS mute.
    piper_binary: str = "piper"
    piper_voice_model: str = ""      # path to a .onnx voice (e.g. en_US-lessac-medium.onnx)
    piper_speaker: int | None = None  # multi-speaker voices: which speaker id

    # Storage
    database_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "jarvis.db")
    memory_context_turns: int = 12

    # Dashboard
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8321

    # Web search (Anthropic server-side tool; ~$0.01 per search + tokens)
    web_search_enabled: bool = True
    web_search_max_uses: int = 5

    # Agent mode (computer use + connected apps)
    agent_enabled: bool = True
    agent_max_steps: int = 15
    agent_auto_approve: bool = False
    agent_allowed_dirs: str = "~"  # comma-separated folders the agent may touch
    mcp_config_path: Path = field(default_factory=lambda: PROJECT_ROOT / "mcp_servers.json")

    # Proactive assistant ("you should know…" nudges)
    proactive_enabled: bool = True
    stale_task_days: int = 7        # open longer than this -> gently flagged
    do_not_disturb: bool = False    # true = never volunteer anything unprompted
    notify_budget: int = 3          # max proactive messages surfaced per check
    proactive_interval_s: int = 3600  # min gap between automatic check-ins

    # Misc
    debug: bool = False
    projects_dir: Path | None = None

    @property
    def data_dir(self) -> Path:
        return self.database_path.parent

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def docs_dir(self) -> Path:
        """Where ingested documents (PDFs, notes) get copied."""
        return self.data_dir / "docs"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.snapshots_dir, self.logs_dir, self.docs_dir):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def llm_available(self) -> bool:
        """Whether the Anthropic API path should be initialised (key + a provider that uses it)."""
        return (self.llm_provider in ("anthropic", "hybrid", "local_first")
                and bool(self.anthropic_api_key))


def load_config(env_file: str | os.PathLike | None = None) -> Config:
    """Build a Config from environment variables (and optional .env file)."""
    if load_dotenv is not None:
        # override=True: .env is the source of truth, so settings edited via the
        # dashboard apply on hot-restart instead of being shadowed by stale os.environ.
        load_dotenv(env_file or PROJECT_ROOT / ".env", override=True)

    db_path = os.getenv("DATABASE_PATH", "")
    database_path = (
        Path(db_path) if os.path.isabs(db_path) else PROJECT_ROOT / db_path
    ) if db_path else PROJECT_ROOT / "data" / "jarvis.db"

    projects_dir_raw = os.getenv("PROJECTS_DIR", "").strip()

    cfg = Config(
        llm_provider=os.getenv("LLM_PROVIDER", "anthropic").strip().lower(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        llm_model_fast=os.getenv("LLM_MODEL_FAST", "claude-haiku-4-5").strip(),
        llm_model_smart=os.getenv("LLM_MODEL_SMART", "claude-sonnet-5").strip(),
        llm_model_deep=os.getenv("LLM_MODEL_DEEP", "claude-opus-4-8").strip(),
        llm_max_tokens=_int(os.getenv("LLM_MAX_TOKENS"), 1024),
        ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").strip().rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:8b").strip(),
        ollama_timeout_s=_int(os.getenv("OLLAMA_TIMEOUT_S"), 120),
        embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text").strip() or "nomic-embed-text",
        obsidian_vault=Path(os.getenv("OBSIDIAN_VAULT", "").strip()
                            or PROJECT_ROOT / "data" / "vault"),
        vision_provider=os.getenv("VISION_PROVIDER", "anthropic").strip().lower(),
        camera_index=_int(os.getenv("CAMERA_INDEX"), 0),
        vision_max_image_edge=_int(os.getenv("VISION_MAX_IMAGE_EDGE"), 1024),
        snapshot_retention_days=_int(os.getenv("SNAPSHOT_RETENTION_DAYS"), 7),
        stt_provider=os.getenv("STT_PROVIDER", "local_whisper").strip().lower(),
        whisper_model_size=os.getenv("WHISPER_MODEL_SIZE", "base").strip(),
        mic_device_index=_opt_int(os.getenv("MIC_DEVICE_INDEX")),
        mic_sample_rate=_int(os.getenv("MIC_SAMPLE_RATE"), 16000),
        wake_word_enabled=_bool(os.getenv("WAKE_WORD_ENABLED"), False),
        wake_word_model=os.getenv("WAKE_WORD_MODEL", "hey_jarvis").strip(),
        wake_word_threshold=_float(os.getenv("WAKE_WORD_THRESHOLD"), 0.5),
        follow_up_listen=_bool(os.getenv("FOLLOW_UP_LISTEN"), True),
        barge_in=_bool(os.getenv("BARGE_IN"), True),
        tts_provider=os.getenv("TTS_PROVIDER", "pyttsx3").strip().lower(),
        tts_rate=_int(os.getenv("TTS_RATE"), 180),
        tts_voice=os.getenv("TTS_VOICE", "").strip(),
        speaker_device_index=_opt_int(os.getenv("SPEAKER_DEVICE_INDEX")),
        piper_binary=os.getenv("PIPER_BINARY", "piper").strip() or "piper",
        piper_voice_model=os.getenv("PIPER_VOICE_MODEL", "").strip(),
        piper_speaker=_opt_int(os.getenv("PIPER_SPEAKER")),
        database_path=database_path,
        memory_context_turns=_int(os.getenv("MEMORY_CONTEXT_TURNS"), 12),
        dashboard_host=os.getenv("DASHBOARD_HOST", "127.0.0.1").strip(),
        dashboard_port=_int(os.getenv("DASHBOARD_PORT"), 8321),
        web_search_enabled=_bool(os.getenv("WEB_SEARCH_ENABLED"), True),
        web_search_max_uses=_int(os.getenv("WEB_SEARCH_MAX_USES"), 5),
        agent_enabled=_bool(os.getenv("AGENT_ENABLED"), True),
        agent_max_steps=_int(os.getenv("AGENT_MAX_STEPS"), 15),
        agent_auto_approve=_bool(os.getenv("AGENT_AUTO_APPROVE"), False),
        agent_allowed_dirs=os.getenv("AGENT_ALLOWED_DIRS", "~").strip() or "~",
        mcp_config_path=Path(os.getenv("MCP_CONFIG_PATH", "").strip() or PROJECT_ROOT / "mcp_servers.json"),
        proactive_enabled=_bool(os.getenv("PROACTIVE_ENABLED"), True),
        stale_task_days=_int(os.getenv("STALE_TASK_DAYS"), 7),
        do_not_disturb=_bool(os.getenv("DO_NOT_DISTURB"), False),
        notify_budget=_int(os.getenv("NOTIFY_BUDGET"), 3),
        proactive_interval_s=_int(os.getenv("PROACTIVE_INTERVAL_S"), 3600),
        debug=_bool(os.getenv("DEBUG"), False),
        projects_dir=Path(projects_dir_raw) if projects_dir_raw else None,
    )
    return cfg
