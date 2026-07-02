"""Local web dashboard + settings app.

Pages:
  /            chat, tasks, notes, scenes, live voice feed
  /settings    edit every setting (devices, API key, wake word, ...) — writes .env
               and hot-restarts the assistant so changes apply immediately.

Local-only by default (binds 127.0.0.1). The CAMERA/MIC indicators in the
header always reflect the real device state.
"""

from __future__ import annotations

import base64
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from app.assistant import Assistant
from app.config import Config, load_config
from app.dashboard import settings as settings_mod
from app.dashboard.settings import (
    SETTINGS_SCHEMA,
    list_audio_devices,
    mask_secret,
    read_env_values,
    scan_cameras,
    update_env_file,
)
from app.logger import get_logger

log = get_logger("dashboard")

VISION_COMMANDS = ("/snapshot", "/desk", "/read", "/ocr", "/look")


def create_app(cfg: Config, assistant: Assistant | None = None,
               env_path: Path | None = None, start_voice: bool = True) -> Flask:
    app = Flask(__name__)
    env_path = env_path or settings_mod.DEFAULT_ENV_PATH
    holder = {"bot": assistant or Assistant(cfg)}
    lock = threading.RLock()  # serialize handle()/restart; SQLite+camera aren't concurrent-safe
    state = {"camera_active": False}

    def bot() -> Assistant:
        return holder["bot"]

    def maybe_start_voice() -> None:
        vl = bot().voice_loop
        if start_voice and vl is not None and vl.available:
            vl.ensure_started()

    maybe_start_voice()

    # ---------- pages -------------------------------------------------------
    @app.get("/")
    def index():
        return render_template("index.html", page="chat")

    @app.get("/settings")
    def settings_page():
        return render_template("settings.html", page="settings")

    # ---------- chat / state -------------------------------------------------
    @app.post("/api/chat")
    def chat():
        data = request.get_json(silent=True) or {}
        text = (data.get("message") or "").strip()
        if not text:
            return jsonify({"reply": "Say something first."})
        uses_camera = any(text.startswith(p) for p in VISION_COMMANDS)
        with lock:
            state["camera_active"] = uses_camera
            try:
                reply = bot().handle(text)
            finally:
                state["camera_active"] = False
        if reply.text and reply.speak:
            bot().speaker.speak(reply.text)
        return jsonify({"reply": reply.text})

    @app.get("/api/state")
    def get_state():
        b = bot()
        vl = b.voice_loop
        return jsonify({
            "camera_active": state["camera_active"],
            "llm_available": b.llm.available,
            "camera_available": b.camera.available,
            "tts_available": b.speaker.available,
            "mic_listening": bool(vl and vl.listening),
            "wake_word_enabled": vl is not None,
            "reminders_due": b.due_reminder_messages(),
        })

    @app.get("/api/activity")
    def activity():
        since = request.args.get("since", 0, type=int)
        items = bot().activity_since(since)
        return jsonify({"items": items,
                        "latest": items[-1]["seq"] if items else since})

    @app.get("/api/tasks")
    def tasks():
        return jsonify([dict(r) for r in bot().db.list_tasks(include_done=True)])

    @app.get("/api/notes")
    def notes():
        return jsonify([dict(r) for r in bot().db.list_notes(20)])

    @app.get("/api/scenes")
    def scenes():
        return jsonify([dict(r) for r in bot().db.recent_scenes(5)])

    @app.post("/api/stop")
    def stop_speaking():
        bot().speaker.stop()
        return jsonify({"ok": True})

    @app.post("/api/mic")
    def mic_toggle():
        """Turn hands-free listening on/off from the header button."""
        want_on = bool((request.get_json(silent=True) or {}).get("on"))
        vl = bot().voice_loop
        if vl is None:
            return jsonify({"ok": False,
                            "message": "Hands-free mode is disabled — enable the wake word "
                                       "in Settings and press Apply."})
        if want_on:
            if not vl.available:
                return jsonify({"ok": False, "message": vl.why_unavailable()})
            vl.wake_up()
            return jsonify({"ok": True, "message": "Listening — say 'jarvis'."})
        vl.go_to_sleep()
        return jsonify({"ok": True, "message": "Microphone off."})

    @app.get("/snapshots/<path:filename>")
    def snapshot_file(filename: str):
        return send_from_directory(cfg.snapshots_dir, filename)

    # ---------- settings ------------------------------------------------------
    @app.get("/api/settings")
    def get_settings():
        values = read_env_values(env_path)
        values["ANTHROPIC_API_KEY"] = mask_secret(values.get("ANTHROPIC_API_KEY", ""))
        return jsonify({
            "schema": SETTINGS_SCHEMA,
            "values": values,
            "audio": list_audio_devices(),
        })

    @app.post("/api/settings")
    def save_settings():
        updates = request.get_json(silent=True) or {}
        if not isinstance(updates, dict):
            return jsonify({"ok": False, "message": "Bad request body."}), 400
        try:
            written = update_env_file(updates, env_path)
        except OSError as exc:
            return jsonify({"ok": False,
                            "message": f"Could not write {env_path}: {exc}"}), 500
        return jsonify({"ok": True, "written": written,
                        "message": f"Saved {len(written)} setting(s)."})

    @app.post("/api/restart")
    def restart():
        """Re-create the assistant with fresh config — settings apply instantly."""
        with lock:
            try:
                old = holder["bot"]
                old.close()
            except Exception as exc:
                log.warning("Error closing old assistant: %s", exc)
            new_cfg = load_config(env_path if env_path.exists() else None)
            holder["bot"] = Assistant(new_cfg)
            maybe_start_voice()
        return jsonify({"ok": True, "message": "Settings applied — JARVIS restarted."})

    @app.get("/api/settings/cameras")
    def cameras():
        return jsonify(scan_cameras())

    # ---------- device tests ---------------------------------------------------
    @app.post("/api/test/speaker")
    def test_speaker():
        b = bot()
        if not b.speaker.available:
            return jsonify({"ok": False,
                            "message": "Voice output is off or pyttsx3 isn't installed "
                                       "(pip install pyttsx3; Linux also needs espeak-ng)."})
        b.speaker.speak("Speaker test successful. All systems online.")
        return jsonify({"ok": True, "message": "Playing a test phrase — did you hear it?"})

    @app.post("/api/test/mic")
    def test_mic():
        b = bot()
        if not (b.ptt.available and b.transcriber.available):
            return jsonify({"ok": False, "message": b.ptt.why_unavailable()})
        try:
            import numpy as np
            import sounddevice as sd
            seconds, rate = 4, b.cfg.mic_sample_rate
            with lock:
                state_msg = "Recording 4 seconds — speak now."
                log.info(state_msg)
                audio = sd.rec(int(seconds * rate), samplerate=rate, channels=1,
                               dtype="float32", device=b.cfg.mic_device_index)
                sd.wait()
            audio = audio.flatten()
            if float(np.abs(audio).max() or 0) < 0.005:
                return jsonify({"ok": False,
                                "message": "Recorded silence. Wrong microphone selected, "
                                           "or it's muted — pick another device and retry."})
            text = b.transcriber.transcribe_array(audio, rate)
            return jsonify({"ok": True,
                            "message": f"Heard: “{text}”" if text else
                                       "Picked up sound but couldn't transcribe words — try "
                                       "speaking closer to the mic."})
        except Exception as exc:
            return jsonify({"ok": False, "message": f"Mic test failed: {exc}"})

    @app.post("/api/test/camera")
    def test_camera():
        b = bot()
        with lock:
            state["camera_active"] = True
            try:
                path = b.camera.snapshot()
            except Exception as exc:
                return jsonify({"ok": False, "message": str(exc)})
            finally:
                state["camera_active"] = False
        image_b64 = base64.b64encode(Path(path).read_bytes()).decode()
        return jsonify({"ok": True, "message": f"Snapshot from camera {b.cfg.camera_index}:",
                        "image": f"data:image/jpeg;base64,{image_b64}"})

    @app.post("/api/test/llm")
    def test_llm():
        b = bot()
        if not b.llm.available:
            return jsonify({"ok": False,
                            "message": "No working API key. Paste it above, press "
                                       "Save & Apply, then test again."})
        reply = b.llm.chat("Reply with exactly: connection confirmed.", max_tokens=20)
        ok = "confirmed" in reply.lower()
        return jsonify({"ok": ok, "message": reply if ok else f"API said: {reply}"})

    return app
