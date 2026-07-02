"""Text-to-speech: offline pyttsx3 by default, with a stoppable speaker thread.

Fallback chain: pyttsx3 missing/broken -> text-only mode (never crashes).
"""

from __future__ import annotations

import threading

from app.config import Config
from app.logger import get_logger

log = get_logger("tts")


class Speaker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._thread: threading.Thread | None = None
        self._engine = None
        self._enabled = cfg.tts_provider == "pyttsx3"
        if self._enabled:
            try:
                import pyttsx3  # noqa: F401  (probe the import here, init per-utterance)
            except ImportError:
                log.warning("pyttsx3 not installed — replies will be text-only. "
                            "pip install pyttsx3")
                self._enabled = False

    @property
    def available(self) -> bool:
        return self._enabled

    def speak(self, text: str) -> None:
        """Speak asynchronously so the user can keep typing (and /stop works)."""
        if not self._enabled or not text.strip():
            return
        self.stop()

        def _run() -> None:
            try:
                import pyttsx3

                # Fresh engine per utterance: pyttsx3's runAndWait loop is
                # unreliable when reused across threads.
                engine = pyttsx3.init()
                engine.setProperty("rate", self.cfg.tts_rate)
                self._engine = engine
                engine.say(text)
                engine.runAndWait()
            except Exception as exc:
                log.error("TTS failed: %s (replies stay text-only this session)", exc)
                self._enabled = False
            finally:
                self._engine = None

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Cut off any in-progress speech."""
        engine = self._engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def wait(self) -> None:
        if self._thread and self._thread.is_alive():
            self._thread.join()
