"""Text-to-speech: queued, streamable, stoppable.

Sentences are played from a queue by one worker thread, so streamed LLM
output can start being spoken while the rest is still being written.

macOS quirk handled here: the nsss driver's runAndWait can return before the
audio actually finishes. Each item therefore also honours a minimum duration
estimated from word count, so is_speaking/wait() reflect real audio time —
the hands-free follow-up window depends on this being accurate.

Speaker selection: with SPEAKER_DEVICE_INDEX set, speech renders to a file
and plays on that device via sounddevice+soundfile. Fallback chain:
routed -> direct pyttsx3 -> text-only (never crashes).
"""

from __future__ import annotations

import queue
import tempfile
import threading
import time
from pathlib import Path

from app.config import Config
from app.logger import get_logger

log = get_logger("tts")

_QUEUE_END_POLL_S = 0.05


class Speaker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._worker: threading.Thread | None = None
        self._busy = threading.Event()
        self._skip = threading.Event()  # set by stop(): abandon current + queued
        self._engine = None
        self._enabled = cfg.tts_provider == "pyttsx3"
        self.last_text: str = ""        # what JARVIS last said (echo filtering)
        self._finished_at: float = 0.0  # monotonic time speech last ended
        if self._enabled:
            try:
                import pyttsx3  # noqa: F401  (probe only; engines are per-utterance)
            except ImportError:
                log.warning("pyttsx3 not installed — replies will be text-only. "
                            "pip install pyttsx3")
                self._enabled = False

    # --- state ---------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self._enabled

    @property
    def is_speaking(self) -> bool:
        return self._busy.is_set() or not self._queue.empty()

    @property
    def seconds_since_speech(self) -> float:
        """Time since speech last ended (inf if never spoke; 0 while speaking)."""
        if self.is_speaking:
            return 0.0
        if self._finished_at == 0.0:
            return float("inf")
        return time.monotonic() - self._finished_at

    # --- speaking --------------------------------------------------------------
    def speak(self, text: str) -> None:
        """Replace whatever is being said with this text (async)."""
        if not self._enabled or not text.strip():
            return
        self.stop()
        self.enqueue(text)

    def enqueue(self, text: str) -> None:
        """Queue a chunk (e.g. one streamed sentence) after what's playing."""
        text = text.strip()
        if not self._enabled or not text:
            return
        if not self.is_speaking:
            self.last_text = text  # fresh utterance
        else:
            self.last_text = (self.last_text + " " + text)[-800:]
        self._ensure_worker()
        self._queue.put(text)

    def stop(self) -> None:
        """Cut off current speech and drop anything queued."""
        while True:  # drop queued items
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        self._skip.set()
        engine = self._engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass
        try:
            import sounddevice as sd
            sd.stop()  # cuts routed playback
        except Exception:
            pass
        # give the worker a moment to notice; don't block long
        deadline = time.monotonic() + 1.0
        while self._busy.is_set() and time.monotonic() < deadline:
            time.sleep(_QUEUE_END_POLL_S)
        self._skip.clear()

    def wait(self, timeout: float = 120.0) -> None:
        """Block until everything queued has actually been spoken."""
        deadline = time.monotonic() + timeout
        while self.is_speaking and time.monotonic() < deadline:
            time.sleep(_QUEUE_END_POLL_S)

    # --- worker -------------------------------------------------------------------
    def _ensure_worker(self) -> None:
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._run_worker, daemon=True,
                                            name="jarvis-tts")
            self._worker.start()

    def _run_worker(self) -> None:
        while True:
            text = self._queue.get()
            self._busy.set()
            started = time.monotonic()
            # Minimum realistic duration: some drivers (macOS nsss) return from
            # runAndWait early; without this floor the follow-up listener opens
            # while JARVIS is still mid-sentence.
            est = 0.2 + 60.0 * len(text.split()) / max(80, self.cfg.tts_rate)
            try:
                if not self._skip.is_set():
                    self._play(text)
            except Exception as exc:
                log.error("TTS failed: %s (replies stay text-only this session)", exc)
                self._enabled = False
            if not self._skip.is_set():
                remaining = 0.9 * est - (time.monotonic() - started)
                if remaining > 0:
                    time.sleep(min(remaining, 30.0))
            self._queue.task_done()
            if self._queue.empty():
                self._busy.clear()
                self._finished_at = time.monotonic()

    def _play(self, text: str) -> None:
        import pyttsx3

        engine = pyttsx3.init()  # fresh engine per item: reuse is flaky across threads
        engine.setProperty("rate", self.cfg.tts_rate)
        if self.cfg.tts_voice:
            try:
                engine.setProperty("voice", self.cfg.tts_voice)
            except Exception:
                log.warning("Voice '%s' not found; using system default", self.cfg.tts_voice)
        self._engine = engine
        try:
            if self.cfg.speaker_device_index is not None:
                if self._speak_routed(engine, text):
                    return
                log.warning("Routed playback failed; using system default speaker.")
            engine.say(text)
            engine.runAndWait()
        finally:
            self._engine = None

    def _speak_routed(self, engine, text: str) -> bool:
        """Render speech to a file and play it on the chosen output device."""
        try:
            import sounddevice as sd
            import soundfile as sf
        except ImportError:
            log.warning("Speaker selection needs: pip install sounddevice soundfile")
            return False
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "tts.wav"  # macOS actually writes AIFF; soundfile
                engine.save_to_file(text, str(path))  # detects format from content
                engine.runAndWait()
                if not path.exists() or path.stat().st_size == 0:
                    return False
                data, rate = sf.read(str(path), dtype="float32")
                sd.play(data, rate, device=self.cfg.speaker_device_index)
                sd.wait()
            return True
        except Exception as exc:
            log.error("Routed TTS playback failed on device %s: %s",
                      self.cfg.speaker_device_index, exc)
            return False
