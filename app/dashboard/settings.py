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
        "blurb": "The paid Claude API powers replies and desk vision. One key enables everything.",
        "items": [
            {"key": "ANTHROPIC_API_KEY", "label": "Claude API key", "type": "password",
             "help": "Get one at console.anthropic.com → API keys. Starts with sk-ant-. "
                     "Leave untouched to keep the saved key."},
            {"key": "LLM_MODEL_FAST", "label": "Everyday model (cheap)", "type": "select",
             "choices": ["claude-haiku-4-5", "claude-sonnet-5"],
             "help": "Used for normal chat. Haiku is the cheap sensible default."},
            {"key": "LLM_MODEL_SMART", "label": "Heavy-lifting model", "type": "select",
             "choices": ["claude-sonnet-5", "claude-haiku-4-5"],
             "help": "Used for desk vision, documents and hard questions. "
                     "Pick Haiku here too to minimise cost (weaker vision)."},
            {"key": "LLM_MAX_TOKENS", "label": "Max reply length (tokens)", "type": "number",
             "min": 128, "max": 4096,
             "help": "Longer replies cost more. 1024 ≈ a few paragraphs."},
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
             "choices": ["hey_jarvis", "alexa", "hey_mycroft"],
             "help": "hey_jarvis also fires on a clear 'jarvis'."},
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
             "choices": ["pyttsx3", "none"],
             "help": "pyttsx3 = free offline voice. none = silent, text-only replies."},
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
            {"key": "PROJECTS_DIR", "label": "Default projects folder", "type": "text",
             "help": "Folder /project loads when you don't give a path. Example: "
                     "C:\\Users\\you\\uni or /Users/you/uni"},
            {"key": "DEBUG", "label": "Verbose logging", "type": "toggle",
             "help": "Turn on only when hunting a problem; logs go to data/logs/."},
        ],
    },
]

_ALLOWED_KEYS = {item["key"] for sec in SETTINGS_SCHEMA for item in sec["items"]}
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
    # Never store the mask placeholder as the real API key.
    key = updates.get("ANTHROPIC_API_KEY", "")
    if key.startswith(KEY_MASK_PREFIX) or key.startswith("•"):
        updates.pop("ANTHROPIC_API_KEY")
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
