"""Local web dashboard: chat with JARVIS, see tasks/notes, trigger snapshots.

Local-only by default (binds 127.0.0.1). Shows an explicit CAMERA indicator
whenever a snapshot is being taken — the privacy state is always visible.
"""

from __future__ import annotations

import threading

from flask import Flask, jsonify, render_template, request, send_from_directory

from app.assistant import Assistant
from app.config import Config


def create_app(cfg: Config, assistant: Assistant | None = None) -> Flask:
    app = Flask(__name__)
    bot = assistant or Assistant(cfg)
    lock = threading.Lock()  # serialize handle() calls; SQLite + camera aren't concurrent-safe
    state = {"camera_active": False}

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/api/chat")
    def chat():
        data = request.get_json(silent=True) or {}
        text = (data.get("message") or "").strip()
        if not text:
            return jsonify({"reply": "Say something first."})
        uses_camera = any(
            text.startswith(p) for p in ("/snapshot", "/desk", "/read", "/ocr", "/look")
        )
        with lock:
            state["camera_active"] = uses_camera
            try:
                reply = bot.handle(text)
            finally:
                state["camera_active"] = False
        if reply.text and reply.speak:
            bot.speaker.speak(reply.text)
        return jsonify({"reply": reply.text})

    @app.get("/api/state")
    def get_state():
        return jsonify({
            "camera_active": state["camera_active"],
            "llm_available": bot.llm.available,
            "camera_available": bot.camera.available,
            "tts_available": bot.speaker.available,
            "reminders_due": bot.due_reminder_messages(),
        })

    @app.get("/api/tasks")
    def tasks():
        rows = bot.db.list_tasks(include_done=True)
        return jsonify([dict(r) for r in rows])

    @app.get("/api/notes")
    def notes():
        return jsonify([dict(r) for r in bot.db.list_notes(20)])

    @app.get("/api/scenes")
    def scenes():
        return jsonify([dict(r) for r in bot.db.recent_scenes(5)])

    @app.post("/api/stop")
    def stop_speaking():
        bot.speaker.stop()
        return jsonify({"ok": True})

    @app.get("/snapshots/<path:filename>")
    def snapshot_file(filename: str):
        return send_from_directory(cfg.snapshots_dir, filename)

    return app
