"""Wake word detection ("hey jarvis") via openWakeWord.

Uses the ONNX inference framework on every platform — the default TFLite
runtime has no wheels for Apple Silicon Macs, ONNX works everywhere
(macOS Intel/ARM, Windows, Linux, Raspberry Pi).

Install:  pip install openwakeword onnxruntime

Privacy note: wake-word mode keeps the microphone streaming so the detector
can hear the phrase. Every audio chunk is scored LOCALLY and discarded —
nothing is recorded or uploaded until the wake word fires. Saying "shutdown"
(or /sleep) closes the microphone device entirely. See app/audio/voice_loop.py
for the state machine.
"""

from __future__ import annotations

from app.logger import get_logger

log = get_logger("wakeword")

try:
    import numpy as np
except ImportError:
    np = None

CHUNK_SAMPLES = 1280  # 80ms @ 16kHz — openwakeword's expected frame size


def wake_word_deps_ok() -> bool:
    if np is None:
        return False
    try:
        import openwakeword  # noqa: F401
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


class WakeWordDetector:
    """Feeds 80ms int16 chunks to openWakeWord; process() returns True on detection."""

    def __init__(self, model_name: str = "hey_jarvis", threshold: float = 0.5):
        self.model_name = model_name
        self.threshold = threshold
        self._model = None

    @property
    def available(self) -> bool:
        return wake_word_deps_ok()

    @staticmethod
    def why_unavailable() -> str:
        return ("Wake word needs: pip install openwakeword onnxruntime "
                "(plus sounddevice numpy for the microphone)")

    def load(self) -> None:
        """Download (first run only) and load the model. Raises RuntimeError with a hint."""
        if self._model is not None:
            return
        if not self.available:
            raise RuntimeError(self.why_unavailable())
        try:
            import openwakeword.utils
            from openwakeword.model import Model

            # First run: fetch the wake model + shared feature models (~5MB total).
            openwakeword.utils.download_models([self.model_name])
            self._model = Model(
                wakeword_models=[self.model_name],
                inference_framework="onnx",
            )
            log.info("Wake word model '%s' loaded (onnx)", self.model_name)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load wake word model '{self.model_name}': {exc}. "
                "First run needs internet to download it; also check "
                "`pip install openwakeword onnxruntime` completed."
            ) from exc

    def process(self, chunk_int16: "np.ndarray") -> bool:
        """Score one audio chunk; True exactly when the wake word fires."""
        scores = self._model.predict(np.asarray(chunk_int16, dtype=np.int16).flatten())
        if max(scores.values(), default=0.0) > self.threshold:
            self._model.reset()
            return True
        return False

    def reset(self) -> None:
        """Clear internal audio buffers (call after TTS output or a handled command)."""
        if self._model is not None:
            self._model.reset()
