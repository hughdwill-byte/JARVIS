"""Speech-to-text via faster-whisper (local, free, offline after first model download)."""

from __future__ import annotations

from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

from app.config import Config
from app.logger import get_logger

log = get_logger("stt")


class Transcriber:
    """Lazy-loads the Whisper model on first use (download can take a minute)."""

    MAX_CONSECUTIVE_FAILURES = 3  # transient errors retry; only give up after a streak

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._model = None
        self._fail_count = 0

    @property
    def available(self) -> bool:
        if (self.cfg.stt_provider != "local_whisper" or np is None
                or self._fail_count >= self.MAX_CONSECUTIVE_FAILURES):
            return False
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            log.info("Loading Whisper model '%s' (first run downloads it)...",
                     self.cfg.whisper_model_size)
            print(f"  Loading speech model '{self.cfg.whisper_model_size}' "
                  "(first run downloads ~150MB)...")
            self._model = WhisperModel(
                self.cfg.whisper_model_size, device="cpu", compute_type="int8"
            )
        return self._model

    def transcribe_array(self, audio: "np.ndarray", sample_rate: int) -> str:
        """Transcribe mono float32 audio in [-1, 1]."""
        if not self.available:
            return ""
        try:
            model = self._load()
            if sample_rate != 16000:
                # Whisper wants 16kHz; cheap linear resample is fine for speech.
                target_len = int(len(audio) * 16000 / sample_rate)
                audio = np.interp(
                    np.linspace(0, len(audio), target_len, endpoint=False),
                    np.arange(len(audio)),
                    audio,
                ).astype(np.float32)
            segments, _info = model.transcribe(audio, beam_size=1, language="en")
            self._fail_count = 0
            return " ".join(s.text.strip() for s in segments).strip()
        except Exception as exc:
            self._fail_count += 1
            log.error("Transcription failed (%d/%d): %s — will retry",
                      self._fail_count, self.MAX_CONSECUTIVE_FAILURES, exc)
            return ""

    def transcribe_file(self, path: str | Path) -> str:
        if not self.available:
            return ""
        try:
            segments, _info = self._load().transcribe(str(path), beam_size=1)
            self._fail_count = 0
            return " ".join(s.text.strip() for s in segments).strip()
        except Exception as exc:
            self._fail_count += 1
            log.error("Transcription failed (%d/%d): %s — will retry",
                      self._fail_count, self.MAX_CONSECUTIVE_FAILURES, exc)
            return ""
