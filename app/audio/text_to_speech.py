"""Text-to-speech: offline pyttsx3 by default, with a stoppable speaker thread.

Speaker selection: if SPEAKER_DEVICE_INDEX is set, speech is rendered to a
temp audio file and played through that specific output device (via
sounddevice+soundfile). Otherwise pyttsx3 speaks through the system default.

Fallback chain: routed playback fails -> direct pyttsx3 -> text-only mode.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from app.config import Config
from app.logger import get_logger

log = get_logger("tts")


class Speaker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._thread: threading.Thread | None = None
        self._engine = None
        self._enabled = cfg.tts_provider == "pyttsx3"
        self.last_text: str = ""       # what JARVIS last said (echo filtering)
        self._finished_at: float = 0.0  # monotonic time speech last ended
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

    @property
    def is_speaking(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def seconds_since_speech(self) -> float:
        """Time since speech last ended (inf if never spoke; 0 while speaking)."""
        if self.is_speaking:
            return 0.0
        if self._finished_at == 0.0:
            return float("inf")
        return time.monotonic() - self._finished_at

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
                if self.cfg.tts_voice:
                    try:
                        engine.setProperty("voice", self.cfg.tts_voice)
                    except Exception:
                        log.warning("Voice '%s' not found; using system default",
                                    self.cfg.tts_voice)
                self._engine = engine
                if self.cfg.speaker_device_index is not None:
                    if self._speak_routed(engine, text):
                        return
                    log.warning("Routed playback failed; using system default speaker.")
                engine.say(text)
                engine.runAndWait()
            except Exception as exc:
                log.error("TTS failed: %s (replies stay text-only this session)", exc)
                self._enabled = False
            finally:
                self._engine = None
                self._finished_at = time.monotonic()

        self.last_text = text
        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

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

    def stop(self) -> None:
        """Cut off any in-progress speech."""
        engine = self._engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass
        try:
            import sounddevice as sd
            sd.stop()  # also cuts routed playback
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def wait(self) -> None:
        if self._thread and self._thread.is_alive():
            self._thread.join()
