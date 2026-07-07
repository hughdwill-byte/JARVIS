"""Kokoro neural TTS backend — fully open-source, runs locally, free.

Adapted from OpenJarvis (https://github.com/open-jarvis/OpenJarvis), Apache-2.0.
Original: src/openjarvis/speech/kokoro_tts.py
https://github.com/open-jarvis/OpenJarvis/blob/main/src/openjarvis/speech/kokoro_tts.py

OpenJarvis's version is wired into its own registry/backend abstraction and
returns encoded audio bytes. This is a stripped, JARVIS-native rewrite: no
registry decorator, lazy import-guarded pipeline, and it returns raw float32
samples so the existing Speaker can play them through sounddevice on the
selected output device.

Requires the OPTIONAL `kokoro` package: pip install kokoro
Import-guarded throughout — if kokoro (or numpy) is missing, callers fall back
to the OS voice, so turning Kokoro on can never make JARVIS go mute.
"""

from __future__ import annotations

from app.logger import get_logger

log = get_logger("kokoro")

# Kokoro always synthesises at 24 kHz.
KOKORO_SAMPLE_RATE = 24000
DEFAULT_VOICE = "af_heart"

# A curated subset of Kokoro's English voices for the Settings dropdown.
# (Kokoro ships many more; these are the reliable, natural-sounding ones.)
AVAILABLE_VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah",
    "am_adam", "am_michael", "bf_emma", "bm_george",
]


class KokoroTTS:
    """Thin wrapper around a Kokoro ``KPipeline`` with lazy, guarded loading.

    Nothing heavy happens on construction — the model is only loaded on the
    first successful ``synthesize`` call. ``available()`` just checks that the
    optional dependencies import, so the Speaker can decide whether to offer
    Kokoro at all without paying the model-load cost up front.
    """

    def __init__(self, lang_code: str = "a") -> None:
        # "a" = American English (Kokoro's default). Kept configurable so a
        # future setting could switch accents without touching this class.
        self._lang_code = lang_code
        self._pipeline = None

    @staticmethod
    def available() -> bool:
        """True only if the optional deps are importable (no model load)."""
        try:
            import kokoro  # noqa: F401
            import numpy  # noqa: F401
            return True
        except ImportError:
            return False

    def _ensure_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        from kokoro import KPipeline  # ImportError bubbles to the caller

        log.info("Loading Kokoro voice pipeline (first run downloads the model)...")
        self._pipeline = KPipeline(lang_code=self._lang_code)
        return self._pipeline

    def synthesize(self, text: str, voice: str = DEFAULT_VOICE, speed: float = 1.0):
        """Synthesise ``text`` to mono float32 samples.

        Returns ``(samples, sample_rate)`` where ``samples`` is a numpy float32
        array in [-1, 1]. Raises ``ImportError`` if kokoro/numpy are missing and
        any exception the pipeline throws — the caller (Speaker) catches these
        and falls back to the OS voice.
        """
        import numpy as np

        pipeline = self._ensure_pipeline()
        chunks = []
        # KPipeline yields (graphemes, phonemes, audio) tuples per segment.
        for _graphemes, _phonemes, audio in pipeline(text, voice=voice, speed=speed):
            chunks.append(np.asarray(audio, dtype="float32"))
        if not chunks:
            return np.zeros(0, dtype="float32"), KOKORO_SAMPLE_RATE
        return np.concatenate(chunks), KOKORO_SAMPLE_RATE
