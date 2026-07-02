"""JARVIS core: wires config, memory, brain, vision, audio and tools together.

Used by both the terminal loop (run_assistant.py) and the dashboard
(app/dashboard/server.py) — one Assistant instance, two front-ends.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.audio.push_to_talk import PushToTalk
from app.audio.speech_to_text import Transcriber
from app.audio.text_to_speech import Speaker
from app.brain.llm_client import LLMClient
from app.brain.router import Router
from app.brain.tool_manager import ToolManager
from app.config import Config
from app.logger import get_logger, setup_logging
from app.memory.database import Database
from app.memory.notes import Notes
from app.memory.preferences import Preferences
from app.prompts import build_context_block
from app.tools.code_helper import CodeHelper
from app.tools.documents import DocumentTool
from app.tools.project_files import ProjectTool
from app.tools.reminders import ReminderManager
from app.tools.study_tools import StudyTools, integrity_check
from app.tools.tasks import TaskManager
from app.vision.camera import Camera, CameraError
from app.vision.image_analyzer import ImageAnalyzer, split_summary_and_objects
from app.vision.ocr import read_image_text
from app.vision.scene_memory import SceneMemory

log = get_logger("assistant")


@dataclass
class Reply:
    text: str
    speak: bool = True  # whether TTS should read this aloud


class Assistant:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        setup_logging(cfg)
        cfg.ensure_dirs()

        self.db = Database(cfg.database_path)
        self.llm = LLMClient(cfg)
        self.speaker = Speaker(cfg)
        self.transcriber = Transcriber(cfg)
        self.ptt = PushToTalk(cfg, self.transcriber)
        self.camera = Camera(cfg)
        self.analyzer = ImageAnalyzer(cfg, self.llm)
        self.scene_memory = SceneMemory(self.db)
        self.notes = Notes(self.db)
        self.prefs = Preferences(self.db)
        self.tasks = TaskManager(self.db)
        self.reminders = ReminderManager(self.db)
        self.docs = DocumentTool(cfg, self.llm)
        self.projects = ProjectTool(cfg, self.llm)
        self.study = StudyTools(self.llm)
        self.code = CodeHelper(self.llm)

        self._last_snapshot: str | None = None
        self.tools = ToolManager()
        self._register_tools()
        self.router = Router(self.tools)

        self.camera.prune_old_snapshots()  # enforce privacy retention on boot

    # ------------------------------------------------------------------
    def _register_tools(self) -> None:
        t = self.tools
        t.register("help", "show this list", lambda _: t.help_text(), speak_reply=False)
        # Vision
        t.register("snapshot", "take a desk photo (no analysis)", self._cmd_snapshot)
        t.register("desk", "photo + describe what's on the desk", self._cmd_desk)
        t.register("read", "photo + read visible text (vision LLM)", self._cmd_read)
        t.register("ocr", "photo + local OCR (free, offline)", self._cmd_ocr, speak_reply=False)
        t.register("look", "photo + answer a question about it", self._cmd_look)
        t.register("changes", "what changed since the last /desk", lambda _: self.scene_memory.describe_changes())
        t.register("scenes", "recent desk snapshot history", lambda _: self.scene_memory.history_text(), speak_reply=False)
        # Memory
        t.register("note", "save a note", self.notes.add)
        t.register("notes", "list notes", lambda _: self.notes.list_text(), speak_reply=False)
        t.register("remember", "store a long-term preference", self.prefs.remember)
        t.register("memories", "list stored preferences", lambda _: self.prefs.list_text(), speak_reply=False)
        t.register("forget", "delete a stored preference", self.prefs.forget)
        # Tasks & reminders
        t.register("task", "add a task (optionally: ... due friday)", self.tasks.add)
        t.register("tasks", "list open tasks", lambda _: self.tasks.list_text(), speak_reply=False)
        t.register("done", "complete a task by number", self.tasks.complete)
        t.register("deltask", "delete a task by number", self.tasks.delete)
        t.register("remind", "set a reminder: /remind 25m stretch", self.reminders.add)
        t.register("reminders", "list pending reminders", lambda _: self.reminders.list_text(), speak_reply=False)
        # Documents & projects
        t.register("doc", "ingest + summarise a PDF/text file", self.docs.ingest_and_summarise, speak_reply=False)
        t.register("docq", "ask about the loaded document", self.docs.ask)
        t.register("project", "load a project folder", self.projects.load)
        t.register("projq", "ask about the loaded project", self.projects.ask, speak_reply=False)
        # Study
        t.register("plan", "assignment milestone planner", self.study.assignment_plan, speak_reply=False)
        t.register("flashcards", "generate flashcards", self.study.flashcards, speak_reply=False)
        t.register("explain", "explain a concept in tiers", self.study.explain)
        t.register("timetable", "build a study timetable", self.study.timetable, speak_reply=False)
        t.register("cite", "citation formatting help", self.study.citation_help)
        # Code
        t.register("code", "coding help / debugging", self.code.assist, speak_reply=False)
        t.register("run", "run a small Python snippet (sandboxed)", self.code.run_python, speak_reply=False)
        # Control
        t.register("stop", "stop speaking", self._cmd_stop)
        t.register("voice", "record one voice message (push-to-talk)", self._cmd_voice)
        t.register("clear", "clear conversation history", self._cmd_clear)
        t.register("status", "show device/API status", lambda _: self.status_text(), speak_reply=False)

    # --- command handlers ------------------------------------------------
    def _cmd_snapshot(self, _: str) -> str:
        try:
            path = self.camera.snapshot()
            self._last_snapshot = str(path)
            return f"Snapshot saved to {path}"
        except CameraError as exc:
            return str(exc)

    def _cmd_desk(self, _: str) -> str:
        try:
            path = self.camera.snapshot()
            self._last_snapshot = str(path)
        except CameraError as exc:
            return str(exc)
        analysis = self.analyzer.describe_desk(path)
        summary, objects = split_summary_and_objects(analysis)
        if objects:  # only record scenes that produced an inventory
            self.scene_memory.record(summary, objects, str(path))
        return summary if summary else analysis

    def _cmd_read(self, _: str) -> str:
        try:
            path = self.camera.snapshot()
            self._last_snapshot = str(path)
        except CameraError as exc:
            return str(exc)
        return self.analyzer.read_text(path)

    def _cmd_ocr(self, _: str) -> str:
        try:
            path = self.camera.snapshot()
            self._last_snapshot = str(path)
        except CameraError as exc:
            return str(exc)
        return read_image_text(path)

    def _cmd_look(self, question: str) -> str:
        if not question.strip():
            return "Ask me something about the desk: /look where is my calculator?"
        try:
            path = self.camera.snapshot()
            self._last_snapshot = str(path)
        except CameraError as exc:
            return str(exc)
        return self.analyzer.ask_about(path, question)

    def _cmd_stop(self, _: str) -> str:
        self.speaker.stop()
        return "Stopped."

    def _cmd_voice(self, _: str) -> str:
        transcript = self.ptt.record_once()
        if not transcript:
            return "I didn't catch anything."
        print(f"  You said: {transcript}")
        return self.handle(transcript).text

    def _cmd_clear(self, _: str) -> str:
        self.db.clear_conversation()
        return "Conversation history cleared. Fresh start."

    # --- status / reminders ----------------------------------------------
    def status_text(self) -> str:
        def mark(ok: bool) -> str:
            return "OK " if ok else "-- "
        return "\n".join([
            "Component status:",
            f"  [{mark(self.llm.available)}] LLM brain ({self.cfg.llm_model_fast} / {self.cfg.llm_model_smart})"
            + ("" if self.llm.available else " — set ANTHROPIC_API_KEY in .env"),
            f"  [{mark(self.camera.available)}] Camera (index {self.cfg.camera_index})"
            + ("" if self.camera.available else " — pip install opencv-python"),
            f"  [{mark(self.ptt.available and self.transcriber.available)}] Voice input"
            + ("" if (self.ptt.available and self.transcriber.available) else f" — {self.ptt.why_unavailable()}"),
            f"  [{mark(self.speaker.available)}] Voice output (TTS)"
            + ("" if self.speaker.available else " — pip install pyttsx3"),
            f"  Database: {self.cfg.database_path}",
            f"  Snapshot retention: {self.cfg.snapshot_retention_days} day(s)",
        ])

    def due_reminder_messages(self) -> list[str]:
        return self.reminders.pop_due()

    # --- main entry point --------------------------------------------------
    def handle(self, user_text: str) -> Reply:
        """Process one user input (typed or transcribed) and return the reply."""
        user_text = user_text.strip()
        if not user_text:
            return Reply("", speak=False)

        command, args = self.router.route(user_text)

        if command == "unknown":
            return Reply(f"No command called /{args}. Try /help.", speak=False)

        if command is not None:
            tool = self.tools.get(command)
            try:
                result = tool.handler(args)
            except Exception as exc:  # a tool bug shouldn't kill the loop
                log.exception("Tool /%s crashed", command)
                result = f"That command hit an error: {exc}"
            return Reply(result, speak=tool.speak_reply)

        # Free chat -> LLM with memory + desk context
        blocked = integrity_check(user_text)
        if blocked:
            self.db.add_message("user", user_text)
            self.db.add_message("assistant", blocked)
            return Reply(blocked)

        context = build_context_block(
            scene_summary=self.scene_memory.latest_summary(),
            notes=self.notes.recent_contents(3),
            tasks=self.tasks.open_titles(5),
            preferences=self.prefs.as_context(),
        )
        history = self.db.recent_messages(self.cfg.memory_context_turns)
        reply_text = self.llm.chat(user_text, history=history, context_block=context)
        self.db.add_message("user", user_text)
        self.db.add_message("assistant", reply_text)
        return Reply(reply_text)

    def close(self) -> None:
        self.speaker.stop()
        self.db.close()
