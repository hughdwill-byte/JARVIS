"""Voice latency tracking (evaluation layer).

Records how long the two slow parts of a voice turn take:
  stt  — speech-to-text (mic audio -> words)
  tts  — text-to-speech synthesis (words -> audio, before playback)

A movie JARVIS answers fast; to keep it fast you have to *measure* it. This is
a tiny in-memory ring buffer (no database rows for something this chatty) with
a global record hook, so the Speaker and Transcriber can log timings without
threading an object through every constructor. `/voicestats` prints the summary.
"""

from __future__ import annotations

import threading
from collections import deque

_STAGES = ("stt", "tts")


class LatencyLog:
    def __init__(self, keep: int = 50):
        self._lock = threading.Lock()
        self._samples: dict[str, deque] = {s: deque(maxlen=keep) for s in _STAGES}

    def record(self, stage: str, ms: float) -> None:
        if stage not in self._samples:
            return
        with self._lock:
            self._samples[stage].append(float(ms))

    def summary_text(self) -> str:
        lines = ["Voice latency (recent, in-memory):"]
        any_data = False
        with self._lock:
            for stage, label in (("stt", "Speech-to-text"), ("tts", "TTS synthesis")):
                samples = list(self._samples[stage])
                if not samples:
                    lines.append(f"  {label}: no samples yet.")
                    continue
                any_data = True
                avg = sum(samples) / len(samples)
                lines.append(
                    f"  {label}: {len(samples)} sample(s), "
                    f"avg {avg / 1000:.2f}s, "
                    f"last {samples[-1] / 1000:.2f}s, "
                    f"min {min(samples) / 1000:.2f}s, max {max(samples) / 1000:.2f}s"
                )
        if not any_data:
            lines.append("  (Talk to JARVIS by voice, then check back — nothing recorded yet.)")
        return "\n".join(lines)


# Global hook so audio components record without constructor plumbing.
# Assistant sets this; None = tracking off (e.g. tests).
LOG: LatencyLog | None = None


def set_log(log: LatencyLog | None) -> None:
    global LOG
    LOG = log


def record(stage: str, ms: float) -> None:
    if LOG is not None:
        LOG.record(stage, ms)
