"""Text-to-speech: queued, streamable, stoppable, no overlap.

Sentences are played from a queue by ONE worker thread, so streamed LLM
output can start being spoken while the rest is still being written — but the
worker only starts the next sentence once the current one has ACTUALLY
finished playing. Getting that "actually finished" right is the whole trick:

- macOS: `pyttsx3`'s runAndWait returns before audio ends (nsss driver), which
  made sentences overlap. So on macOS we shell out to the built-in `say`
  binary, which blocks until playback completes — no overlap, and better
  voices. Voice/rate map straight onto `say -v`/`say -r`.
- Windows/Linux: pyttsx3 runAndWait blocks correctly, so we use it directly.
- A specific output device (SPEAKER_DEVICE_INDEX) is honoured by rendering to
  a file and playing it through sounddevice+soundfile (sd.wait() blocks).

Fallback chain never crashes: preferred path -> pyttsx3 -> text-only.
"""

from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from app.config import Config
from app.logger import get_logger

log = get_logger("tts")

_POLL_S = 0.05
_IS_MAC = sys.platform == "darwin"


class Speaker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._worker: threading.Thread | None = None
        self._busy = threading.Event()
        self._skip = threading.Event()   # set by stop(): abandon current + queued
        self._engine = None              # active pyttsx3 engine (if any)
        self._proc: subprocess.Popen | None = None  # active `say` process (if any)
        self._enabled = cfg.tts_provider == "pyttsx3"
        self.last_text: str = ""         # what JARVIS last said (echo filtering)
        self._finished_at: float = 0.0   # monotonic time speech last ended
        self._say = shutil.which("say") if _IS_MAC else None
        self._voice_name_cache: dict[str, str] | None = None
        if self._enabled and not self._say:
            try:
                import pyttsx3  # noqa: F401  (probe; engines are per-utterance)
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
            self.last_text = text
        else:
            self.last_text = (self.last_text + " " + text)[-800:]
        self._ensure_worker()
        self._queue.put(text)

    def stop(self) -> None:
        """Cut off current speech and drop anything queued."""
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        self._skip.set()
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        deadline = time.monotonic() + 1.5
        while self._busy.is_set() and time.monotonic() < deadline:
            time.sleep(_POLL_S)
        self._skip.clear()

    def wait(self, timeout: float = 120.0) -> None:
        """Block until everything queued has actually been spoken."""
        deadline = time.monotonic() + timeout
        while self.is_speaking and time.monotonic() < deadline:
            time.sleep(_POLL_S)

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
            try:
                if not self._skip.is_set():
                    self._play(text)  # blocks until audio truly finishes
            except Exception as exc:
                log.error("TTS failed: %s (replies stay text-only this session)", exc)
                self._enabled = False
            self._queue.task_done()
            if self._queue.empty():
                self._busy.clear()
                self._finished_at = time.monotonic()

    # --- playback backends --------------------------------------------------------
    def _play(self, text: str) -> None:
        if self.cfg.speaker_device_index is not None and self._play_routed(text):
            return
        if self._say:
            self._play_macos_say(text)
        else:
            self._play_pyttsx3(text)

    def _play_macos_say(self, text: str) -> None:
        """macOS `say` blocks until playback completes — no overlap."""
        cmd = [self._say, "-r", str(self.cfg.tts_rate)]
        name = self._say_voice_name()
        if name:
            cmd += ["-v", name]
        cmd.append(text)
        try:
            self._proc = subprocess.Popen(cmd)
            self._proc.wait()
        except Exception as exc:
            log.error("`say` failed (%s); falling back to pyttsx3", exc)
            self._say = None  # stop trying it this session
            self._play_pyttsx3(text)
        finally:
            self._proc = None

    def _play_pyttsx3(self, text: str) -> None:
        import pyttsx3

        engine = pyttsx3.init()  # fresh per item: reuse is flaky across threads
        engine.setProperty("rate", self.cfg.tts_rate)
        if self.cfg.tts_voice:
            try:
                engine.setProperty("voice", self.cfg.tts_voice)
            except Exception:
                log.warning("Voice '%s' not found; using default", self.cfg.tts_voice)
        self._engine = engine
        try:
            engine.say(text)
            engine.runAndWait()
        finally:
            self._engine = None

    def _play_routed(self, text: str) -> bool:
        """Render to a file and play on the chosen output device (sd.wait blocks)."""
        try:
            import sounddevice as sd
            import soundfile as sf
        except ImportError:
            log.warning("Speaker selection needs: pip install sounddevice soundfile")
            return False
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "tts.wav"
                if self._say:
                    cmd = [self._say, "-r", str(self.cfg.tts_rate), "-o", str(path),
                           "--data-format=LEF32@22050"]
                    name = self._say_voice_name()
                    if name:
                        cmd += ["-v", name]
                    cmd.append(text)
                    subprocess.run(cmd, check=True)
                else:
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.setProperty("rate", self.cfg.tts_rate)
                    if self.cfg.tts_voice:
                        try:
                            engine.setProperty("voice", self.cfg.tts_voice)
                        except Exception:
                            pass
                    engine.save_to_file(text, str(path))
                    engine.runAndWait()
                if not path.exists() or path.stat().st_size == 0:
                    return False
                data, rate = sf.read(str(path), dtype="float32")
                sd.play(data, rate, device=self.cfg.speaker_device_index)
                sd.wait()
            return True
        except Exception as exc:
            log.error("Routed playback failed on device %s: %s",
                      self.cfg.speaker_device_index, exc)
            return False

    def _say_voice_name(self) -> str:
        """Map the stored pyttsx3 voice id to a `say -v` name (e.g. 'Jamie')."""
        raw = self.cfg.tts_voice
        if not raw:
            return ""
        # If it already looks like a plain name, use it.
        if "." not in raw:
            return raw.split(" (")[0]
        if self._voice_name_cache is None:
            self._voice_name_cache = {}
            try:
                import pyttsx3
                eng = pyttsx3.init()
                for v in eng.getProperty("voices") or []:
                    self._voice_name_cache[v.id] = (v.name or "").split(" (")[0]
                try:
                    eng.stop()
                except Exception:
                    pass
            except Exception:
                pass
        return self._voice_name_cache.get(raw, "")
