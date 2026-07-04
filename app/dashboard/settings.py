"""Settings backend for the dashboard: schema, .env editing, device discovery.

Everything a non-technical user needs to change lives here, described by
SETTINGS_SCHEMA. The Settings page renders itself from this schema, so adding
a new option is one dict — no HTML edits.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from app.config import PROJECT_ROOT
from app.logger import get_logger

log = get_logger("settings")

DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
KEY_MASK_PREFIX = "••••"  # •••• — never written back to .env

# Field types the settings page knows how to render:
#   text, password, number, slider, toggle, select
# "source" on a select pulls live options: mic_devices / speaker_devices / cameras
SETTINGS_SCHEMA: list[dict] = [
    {
        "section": "AI Brain",
        "blurb": "Claude powers replies, desk vision, and tasks — via the API (a key), "
                 "your Claude Pro subscription (Claude Code), or a mix of both.",
        "items": [
            {"key": "LLM_PROVIDER", "label": "Brain source", "type": "select",
             "choices": ["anthropic", "local_first", "hybrid", "claude_code", "ollama", "none"],
             "help": "anthropic = API key (fastest replies, pay-as-you-go). "
                     "local_first = everyday chat on a FREE local model via Ollama, "
                     "cloud only for hard/vision/agent work — cheapest and most "
                     "private (install ollama.com, then 'ollama pull qwen3:8b'). "
                     "claude_code = your Claude Pro/Max subscription, no API cost but "
                     "~4-8s per reply. hybrid = chat on the API, big tasks on your "
                     "subscription. ollama = local only ($0, offline; no agent/vision). "
                     "none = offline."},
            {"key": "ANTHROPIC_API_KEY", "label": "Claude API key", "type": "password",
             "help": "Needed for 'anthropic' and 'hybrid'. Get one at console.anthropic.com "
                     "→ API keys. Starts with sk-ant-. Leave untouched to keep the saved key."},
            {"key": "LLM_MODEL_FAST", "label": "Everyday model (cheap)", "type": "select",
             "choices": ["claude-haiku-4-5", "claude-sonnet-5"],
             "help": "Used for normal chat. Haiku is the cheap sensible default."},
            {"key": "LLM_MODEL_SMART", "label": "Heavy-lifting model", "type": "select",
             "choices": ["claude-sonnet-5", "claude-haiku-4-5"],
             "help": "Used for desk vision, documents and hard questions. "
                     "Pick Haiku here too to minimise cost (weaker vision)."},
            {"key": "LLM_MODEL_DEEP", "label": "Deep-work model (on demand)", "type": "select",
             "choices": ["claude-opus-4-8", "claude-sonnet-5"],
             "help": "Only used when you ask for heavy output — say 'in-depth', "
                     "'deep dive', 'comprehensive', or 'use opus' in your request. "
                     "Opus is the strongest and priciest model; it never runs on "
                     "ordinary chat. Pick Sonnet here to opt out of the extra cost."},
            {"key": "LLM_MAX_TOKENS", "label": "Max reply length (tokens)", "type": "number",
             "min": 128, "max": 4096,
             "help": "Longer replies cost more. 1024 ≈ a few paragraphs."},
            {"key": "OLLAMA_MODEL", "label": "Local model (Ollama)", "type": "select",
             "choices": ["qwen3:8b", "llama3.2", "gemma3", "qwen3:4b"],
             "help": "Used by 'local_first' and 'ollama' brain sources. qwen3:8b is the "
                     "best all-rounder on ~8GB; qwen3:4b for weaker machines. "
                     "Install first: ollama pull <model>."},
            {"key": "OLLAMA_HOST", "label": "Ollama address", "type": "text",
             "help": "Where the local model server runs. Default is this computer "
                     "(http://127.0.0.1:11434); change only if Ollama runs on another "
                     "machine on your network."},
            {"key": "WEB_SEARCH_ENABLED", "label": "Web search", "type": "toggle",
             "help": "Lets JARVIS look things up (news, sports scores, prices, docs). "
                     "Costs about 1 cent per search on the API backend."},
        ],
    },
    {
        "section": "Microphone & Speech",
        "blurb": "Which mic JARVIS listens through, and how speech becomes text (all local & free).",
        "items": [
            {"key": "MIC_DEVICE_INDEX", "label": "Microphone", "type": "select",
             "source": "mic_devices",
             "help": "Pick your desk speakerphone, not the laptop's built-in mic."},
            {"key": "STT_PROVIDER", "label": "Speech-to-text", "type": "select",
             "choices": ["local_whisper", "none"],
             "help": "local_whisper = free, offline. none = typing only."},
            {"key": "WHISPER_MODEL_SIZE", "label": "Speech model size", "type": "select",
             "choices": ["tiny", "base", "small", "medium"],
             "help": "Bigger = more accurate but slower. base is the sweet spot; "
                     "use tiny on a Raspberry Pi."},
        ],
    },
    {
        "section": "Hands-free wake word",
        "blurb": "Say 'jarvis' to talk without typing. Audio is checked locally and discarded — "
                 "nothing is stored or uploaded until the wake word fires. Say 'shutdown' to "
                 "close the mic completely.",
        "items": [
            {"key": "WAKE_WORD_ENABLED", "label": "Hands-free mode", "type": "toggle",
             "help": "Off = strict push-to-talk only (mic never opens by itself)."},
            {"key": "WAKE_WORD_THRESHOLD", "label": "Wake sensitivity", "type": "slider",
             "min": 0.3, "max": 0.8, "step": 0.05,
             "help": "Lower = easier to trigger (more false alarms from TV/music). "
                     "Raise to 0.6 if it self-triggers; lower to 0.4 if it misses you."},
            {"key": "WAKE_WORD_MODEL", "label": "Wake phrase", "type": "select",
             "choices": ["hey_jarvis", "alexa", "hey_mycroft", "hey_rhasspy"],
             "help": "hey_jarvis fires on BOTH 'hey jarvis' and a clear 'jarvis' — it's "
                     "the one you want. The others are alternative pre-trained phrases "
                     "('alexa', 'hey mycroft', 'hey rhasspy'). Fully custom phrases would "
                     "need training a detection model (openwakeword docs) — not built in."},
            {"key": "FOLLOW_UP_LISTEN", "label": "Conversation mode", "type": "toggle",
             "help": "After JARVIS answers, it keeps listening ~8 seconds so you can reply "
                     "without saying the wake phrase again. Stay quiet to end the "
                     "conversation."},
            {"key": "BARGE_IN", "label": "Interrupt by talking", "type": "toggle",
             "help": "Talk over JARVIS (clearly, for half a second) and it stops and "
                     "listens to you instead. Turn off if loud speakers make it "
                     "self-interrupt."},
        ],
    },
    {
        "section": "Speaker & Voice output",
        "blurb": "How JARVIS talks back.",
        "items": [
            {"key": "SPEAKER_DEVICE_INDEX", "label": "Speaker", "type": "select",
             "source": "speaker_devices",
             "help": "System default follows your OS sound settings; pick a specific "
                     "device to lock JARVIS to it."},
            {"key": "TTS_PROVIDER", "label": "Voice output", "type": "select",
             "choices": ["pyttsx3", "piper", "none"],
             "help": "pyttsx3 = free offline OS voice (robotic but zero setup). "
                     "piper = natural offline neural voice (needs the piper binary + "
                     "a downloaded .onnx voice; set it below). none = text-only. "
                     "If piper isn't set up, JARVIS quietly falls back to the OS voice."},
            {"key": "PIPER_VOICE_MODEL", "label": "Piper voice model (.onnx)", "type": "text",
             "help": "Only for the 'piper' voice. Full path to a downloaded voice file, "
                     "e.g. ~/piper/en_US-lessac-medium.onnx. Get voices from "
                     "github.com/rhasspy/piper/releases (download the .onnx AND its "
                     ".onnx.json into the same folder)."},
            {"key": "TTS_VOICE", "label": "Voice", "type": "select",
             "source": "tts_voices",
             "help": "Your operating system's speech voices. macOS tip: get much nicer "
                     "ones free via System Settings → Accessibility → Spoken Content → "
                     "System voice → Manage Voices — download an 'Enhanced'/'Premium' "
                     "voice, then Rescan here and pick it."},
            {"key": "TTS_RATE", "label": "Speaking speed (words/min)", "type": "slider",
             "min": 120, "max": 230, "step": 5,
             "help": "160–190 sounds most natural."},
        ],
    },
    {
        "section": "Camera & Vision",
        "blurb": "The camera only turns on for explicit commands like /desk — never by itself.",
        "items": [
            {"key": "CAMERA_INDEX", "label": "Camera", "type": "select",
             "source": "cameras",
             "help": "Laptops: 0 is usually the built-in camera, 1 the USB desk camera. "
                     "Use 'Scan for cameras' then 'Test camera' to confirm."},
            {"key": "VISION_PROVIDER", "label": "Desk image analysis", "type": "select",
             "choices": ["anthropic", "none"],
             "help": "anthropic = snapshots can be described/read (uses the API). "
                     "none = snapshots stay on this computer only."},
            {"key": "VISION_MAX_IMAGE_EDGE", "label": "Image detail sent to AI", "type": "select",
             "choices": ["768", "1024", "1568"],
             "help": "Bigger reads small text better but costs more per snapshot."},
            {"key": "SNAPSHOT_RETENTION_DAYS", "label": "Keep snapshots for (days)",
             "type": "number", "min": 0, "max": 365,
             "help": "0 = delete photos right after analysis. Descriptions are kept as text."},
        ],
    },
    {
        "section": "Computer & Apps",
        "blurb": "When a request needs it, JARVIS completes tasks using this computer "
                 "(files, commands) and connected apps like email or calendar (set up via "
                 "mcp_servers.json — see docs/COMPUTER_AND_APPS.md) — automatically, in "
                 "normal conversation. Risky actions always ask you first unless you opt "
                 "in below.",
        "items": [
            {"key": "AGENT_ENABLED", "label": "Agent mode", "type": "toggle",
             "help": "Off = /agent is disabled entirely; JARVIS can't touch files or apps."},
            {"key": "AGENT_ALLOWED_DIRS", "label": "Folders it may touch", "type": "text",
             "help": "Comma-separated. ~ means your whole home folder; tighten to e.g. "
                     "~/Downloads,~/uni if you prefer."},
            {"key": "AGENT_AUTO_APPROVE", "label": "Act without asking", "type": "toggle",
             "help": "Off (recommended): every file write, command, or email send asks you "
                     "first in the terminal. On: it just acts — required for agent tasks "
                     "started from this app window."},
            {"key": "AGENT_MAX_STEPS", "label": "Max steps per task", "type": "number",
             "min": 3, "max": 40,
             "help": "How many tool actions one /agent task may take. More = bigger tasks, "
                     "higher cost."},
        ],
    },
    {
        "section": "Advanced",
        "blurb": "You rarely need to touch these.",
        "items": [
            {"key": "MEMORY_CONTEXT_TURNS", "label": "Conversation memory (turns)",
             "type": "number", "min": 2, "max": 40,
             "help": "How much recent chat the AI sees each time. More = smarter follow-ups, "
                     "higher cost."},
            {"key": "DASHBOARD_PORT", "label": "Dashboard port", "type": "number",
             "min": 1024, "max": 65535,
             "help": "Change if 8321 clashes with something. Takes effect on next app start."},
            {"key": "OBSIDIAN_VAULT", "label": "Markdown/Obsidian vault folder", "type": "text",
             "help": "Where /export writes notes, memories and tasks as Markdown. "
                     "Point it at a folder inside your Obsidian vault to browse "
                     "JARVIS memory there. Default: data/vault."},
            {"key": "PROJECTS_DIR", "label": "Default projects folder", "type": "text",
             "help": "Folder /project loads when you don't give a path. Example: "
                     "C:\\Users\\you\\uni or /Users/you/uni"},
            {"key": "HF_TOKEN", "label": "Hugging Face token (optional)", "type": "password",
             "help": "Only silences the 'unauthenticated requests to the HF Hub' warning "
                     "and speeds up the one-time speech-model download. Free: "
                     "huggingface.co → sign up → Settings → Access Tokens → New token "
                     "(Read). Fine to leave empty."},
            {"key": "DEBUG", "label": "Verbose logging", "type": "toggle",
             "help": "Turn on only when hunting a problem; logs go to data/logs/."},
        ],
    },
]

_ALLOWED_KEYS = {item["key"] for sec in SETTINGS_SCHEMA for item in sec["items"]}
# Keys managed by dedicated UI widgets rather than plain schema fields:
_ALLOWED_KEYS |= {"TTS_FAVOURITE_VOICES"}  # comma-separated voice ids, pinned first
SECRET_KEYS = {"ANTHROPIC_API_KEY", "HF_TOKEN"}  # masked in the UI, never echoed back
_ENV_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")


# --- .env reading/writing -------------------------------------------------

def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _ENV_LINE.match(line)
            if m and m.group(1) in _ALLOWED_KEYS:
                values[m.group(1)] = line.split("=", 1)[1].strip()
    return values


def read_env_values(env_path: Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    """Current values for schema keys: .env, then process env, then .env.example defaults."""
    values = _parse_env(env_path)
    example = _parse_env(env_path.parent / ".env.example")
    for key in _ALLOWED_KEYS:
        if key not in values:
            values[key] = os.getenv(key) or example.get(key, "")
    return values


def update_env_file(updates: dict[str, str], env_path: Path = DEFAULT_ENV_PATH) -> list[str]:
    """Write settings into .env, preserving comments/layout. Returns keys written."""
    updates = {k: str(v).strip() for k, v in updates.items() if k in _ALLOWED_KEYS}
    # Never store a mask placeholder as a real secret.
    for secret in SECRET_KEYS:
        value = updates.get(secret, "")
        if value.startswith(KEY_MASK_PREFIX) or value.startswith("•"):
            updates.pop(secret)
    if not updates:
        return []

    if not env_path.exists():
        example = env_path.parent / ".env.example"
        if example.exists():
            shutil.copy(example, env_path)
        else:
            env_path.write_text("", encoding="utf-8")

    lines = env_path.read_text(encoding="utf-8").splitlines()
    written: set[str] = set()
    for i, line in enumerate(lines):
        m = _ENV_LINE.match(line)
        if m and m.group(1) in updates and m.group(1) not in written:
            lines[i] = f"{m.group(1)}={updates[m.group(1)]}"
            written.add(m.group(1))
    missing = [k for k in updates if k not in written]
    if missing:
        lines.append("")
        lines.extend(f"{k}={updates[k]}" for k in missing)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("Settings saved to %s: %s", env_path, ", ".join(sorted(updates)))
    return sorted(updates)


def mask_secret(value: str) -> str:
    if not value:
        return ""
    return KEY_MASK_PREFIX + value[-4:] if len(value) > 8 else KEY_MASK_PREFIX


# --- device discovery -------------------------------------------------------

def list_audio_devices() -> dict:
    """Input/output devices for the dropdowns; helpful hint if audio libs missing."""
    try:
        import sounddevice as sd
    except ImportError:
        return {"inputs": [], "outputs": [],
                "error": "Audio device listing needs: pip install sounddevice numpy"}
    try:
        devices = sd.query_devices()
        default_in, default_out = sd.default.device
    except Exception as exc:
        return {"inputs": [], "outputs": [], "error": f"Could not query audio devices: {exc}"}
    inputs, outputs = [], []
    for i, d in enumerate(devices):
        entry = {"index": i, "name": d["name"]}
        if d["max_input_channels"] > 0:
            inputs.append({**entry, "default": i == default_in})
        if d["max_output_channels"] > 0:
            outputs.append({**entry, "default": i == default_out})
    return {"inputs": inputs, "outputs": outputs, "error": None}


def list_tts_voices() -> list[dict]:
    """System speech voices for the Settings dropdown (name shown, id stored)."""
    try:
        import pyttsx3
    except ImportError:
        return []
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty("voices") or []
        out = []
        for v in voices:
            langs = getattr(v, "languages", None)
            lang = ""
            if langs:
                first = langs[0]
                lang = f" ({first.decode() if isinstance(first, bytes) else first})"
            out.append({"index": v.id, "name": f"{v.name}{lang}"})
        try:
            engine.stop()
        except Exception:
            pass
        return out
    except Exception as exc:
        log.warning("Could not list TTS voices: %s", exc)
        return []


def scan_cameras(max_index: int = 5) -> dict:
    """Probe camera indexes 0..max_index. Slow-ish (a second or two) — on demand only."""
    try:
        import cv2
    except ImportError:
        return {"cameras": [], "error": "Camera scanning needs: pip install opencv-python"}
    found = []
    for i in range(max_index + 1):
        cap = cv2.VideoCapture(i)
        try:
            if cap.isOpened():
                ok, frame = cap.read()
                if ok and frame is not None:
                    h, w = frame.shape[:2]
                    found.append({"index": i, "label": f"Camera {i} ({w}x{h})"})
        finally:
            cap.release()
    return {"cameras": found,
            "error": None if found else "No cameras responded. Check USB and close other "
                                        "apps using the camera, then scan again."}
