"""Cross-platform 'is JARVIS working?' indicator.

The app's desktop window owns the GUI thread, so JARVIS writes its current
state — listening / thinking / speaking — to a tiny JSON file, and a *separate*
process (app/ui/status_overlay.py) reads that file and shows a small coloured
dot in the menu bar / system tray. Running it as its own process keeps it
completely decoupled from the app (it can never freeze or crash the assistant)
and, being a menu-bar item, it never covers the screen or blocks clicks.

This module is the writer side: a background poller derives the state from
things JARVIS already exposes (is the speaker talking? is the mic capturing an
utterance? is a reply being generated?) and writes it out. No Tkinter here, so
it's safe to import anywhere.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from app.config import PROJECT_ROOT, Config
from app.logger import get_logger

log = get_logger("status")

POLL_S = 0.15
STATE_FILE = "status.json"

# The states the overlay knows how to render, in priority order (first match
# wins when several are momentarily true — e.g. speaking beats a lingering
# thinking flag).
STATES = ("speaking", "thinking", "listening", "armed", "idle")


def read_state(path: str | Path) -> tuple[str, float]:
    """Read (state, timestamp) from the state file. ('idle', 0.0) on any problem."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return str(data.get("state", "idle")), float(data.get("ts", 0.0))
    except Exception:
        return "idle", 0.0


class StatusIndicator:
    """Derives and publishes JARVIS's working state; optionally spawns the overlay.

    Inert unless ``cfg.status_overlay`` is on — ``set_thinking`` / ``set_recording``
    are always safe to call (cheap attribute writes), but no thread or subprocess
    starts and nothing is written until ``start()`` runs with the toggle enabled.
    """

    def __init__(self, cfg: Config, speaker, voice_loop_getter: Callable[[], object]):
        self.cfg = cfg
        self._speaker = speaker
        self._voice_loop_getter = voice_loop_getter
        self.thinking = False      # set around LLM/tool work
        self.recording = False     # set while the mic captures your utterance
        self._state_path = cfg.data_dir / STATE_FILE
        self._last: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None
        self._started = False

    # --- state derivation ----------------------------------------------------
    def current_state(self) -> str:
        if getattr(self._speaker, "is_speaking", False):
            return "speaking"
        if self.thinking:
            return "thinking"
        if self.recording:
            return "listening"
        vl = self._voice_loop_getter()
        if vl is not None and getattr(vl, "listening", False):
            return "armed"  # hands-free on, waiting for the wake word
        return "idle"

    # --- transient flags (called from the assistant / voice loop) ------------
    def set_thinking(self, value: bool) -> None:
        self.thinking = value

    def set_recording(self, value: bool) -> None:
        self.recording = value

    # --- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        if not self.cfg.status_overlay or self._started:
            return
        self._started = True
        self._write("idle")
        self._launch_overlay()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="jarvis-status")
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(POLL_S):
            state = self.current_state()
            if state != self._last:
                self._last = state
                self._write(state)

    def _write(self, state: str) -> None:
        try:
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"state": state, "ts": time.time()}),
                           encoding="utf-8")
            tmp.replace(self._state_path)  # atomic-ish, no half-written reads
        except Exception as exc:
            log.debug("status write failed: %s", exc)

    def _launch_overlay(self) -> None:
        # On Windows, stop a console window flashing up for the child process —
        # that would itself be "interfering". No-op elsewhere.
        extra = {}
        if sys.platform.startswith("win"):
            extra["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-m", "app.ui.status_overlay",
                 "--state-file", str(self._state_path)],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                **extra,
            )
            log.info("Status overlay launched (pid %s)", self._proc.pid)
        except Exception as exc:
            log.warning("Could not launch the status overlay: %s", exc)
            self._proc = None

    def close(self) -> None:
        if not self._started:
            return
        self._stop.set()
        self._write("idle")
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
