"""Wake word support ("hey jarvis") via openWakeWord — OPTIONAL upgrade.

Not part of the MVP loop: push-to-talk is more reliable and doesn't keep the
microphone open. Enable later by installing `openwakeword` and wiring
WakeWordListener into run_assistant.py (see README "Voice upgrade").

Privacy note: wake-word mode keeps the mic streaming continuously so the
detector can hear the phrase. Audio is processed locally in small chunks and
never leaves the machine, but the [MIC ACTIVE] state is on the whole time —
that's why it is opt-in.
"""

from __future__ import annotations

from typing import Callable

from app.config import Config
from app.logger import get_logger

log = get_logger("wakeword")

try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    sd = None
    np = None


class WakeWordListener:
    def __init__(self, cfg: Config, on_wake: Callable[[], None],
                 model_name: str = "hey_jarvis", threshold: float = 0.6):
        self.cfg = cfg
        self.on_wake = on_wake
        self.model_name = model_name
        self.threshold = threshold
        self._stop = False

    @property
    def available(self) -> bool:
        if sd is None:
            return False
        try:
            import openwakeword  # noqa: F401
            return True
        except ImportError:
            return False

    def listen_forever(self) -> None:
        """Blocking loop: call on_wake() each time the wake word is heard."""
        if not self.available:
            print("Wake word needs: pip install openwakeword sounddevice numpy")
            return

        from openwakeword.model import Model

        oww = Model(wakeword_models=[self.model_name])
        chunk = 1280  # 80ms at 16kHz, openwakeword's expected frame
        print("  [MIC ACTIVE — wake word mode] Say 'hey jarvis'. Ctrl+C to stop.")
        try:
            with sd.InputStream(samplerate=16000, channels=1, dtype="int16",
                                blocksize=chunk, device=self.cfg.mic_device_index) as stream:
                while not self._stop:
                    audio, _ = stream.read(chunk)
                    scores = oww.predict(np.frombuffer(audio, dtype=np.int16))
                    if scores.get(self.model_name, 0) > self.threshold:
                        log.info("Wake word detected")
                        oww.reset()
                        self.on_wake()
        except KeyboardInterrupt:
            pass
        finally:
            print("  [MIC OFF]")

    def stop(self) -> None:
        self._stop = True
