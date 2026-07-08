"""Kokoro neural TTS: selection logic, graceful fallback, and config wiring.

No audio hardware, no `kokoro` package, and no model download are needed — we
mock the kokoro import and the sounddevice playback, which is where the real
decision/fallback bugs would live.
"""

import sys
import types

import numpy as np

from app.audio.text_to_speech import Speaker
from app.config import Config, load_config


def _cfg(tmp_path, **kw):
    base = dict(
        llm_provider="none", vision_provider="none", stt_provider="none",
        database_path=tmp_path / "t.db", mcp_config_path=tmp_path / "m.json",
    )
    base.update(kw)
    return Config(**base)


def _install_fake_kokoro(monkeypatch):
    """Put a fake `kokoro` module on sys.modules so KokoroTTS.available() → True
    and its pipeline yields deterministic audio."""
    class _FakeKPipeline:
        def __init__(self, lang_code="a"):
            self.lang_code = lang_code

        def __call__(self, text, voice="af_heart", speed=1.0):
            _FakeKPipeline.last = {"text": text, "voice": voice, "speed": speed}
            yield ("g", "p", np.array([0.0, 0.1], dtype="float32"))
            yield ("g", "p", np.array([0.2, 0.3], dtype="float32"))

    fake = types.ModuleType("kokoro")
    fake.KPipeline = _FakeKPipeline
    monkeypatch.setitem(sys.modules, "kokoro", fake)
    return _FakeKPipeline


# --- selection logic ---------------------------------------------------------

def test_engine_system_never_enables_kokoro(tmp_path, monkeypatch):
    _install_fake_kokoro(monkeypatch)  # kokoro IS importable…
    sp = Speaker(_cfg(tmp_path, tts_engine="system"))  # …but engine=system opts out
    assert sp._kokoro is None


def test_engine_auto_enables_kokoro_when_installed(tmp_path, monkeypatch):
    _install_fake_kokoro(monkeypatch)
    sp = Speaker(_cfg(tmp_path, tts_engine="auto"))
    assert sp._kokoro is not None
    assert sp.available is True  # enabled even without pyttsx3, thanks to Kokoro


def test_engine_auto_without_kokoro_falls_back(tmp_path, monkeypatch):
    # Ensure kokoro is NOT importable.
    monkeypatch.setitem(sys.modules, "kokoro", None)
    kokoro_speaker = Speaker(_cfg(tmp_path, tts_engine="auto"))
    system_speaker = Speaker(_cfg(tmp_path, tts_engine="system"))
    assert kokoro_speaker._kokoro is None
    # Choosing the neural engine must never leave TTS more disabled than the
    # plain system path would on the same machine.
    assert kokoro_speaker.available == system_speaker.available


def test_engine_kokoro_forced_but_absent_is_not_mute(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "kokoro", None)
    forced = Speaker(_cfg(tmp_path, tts_engine="kokoro"))
    system = Speaker(_cfg(tmp_path, tts_engine="system"))
    assert forced._kokoro is None
    assert forced.available == system.available


def test_provider_none_disables_kokoro_too(tmp_path, monkeypatch):
    _install_fake_kokoro(monkeypatch)
    sp = Speaker(_cfg(tmp_path, tts_provider="none", tts_engine="kokoro"))
    assert sp.available is False
    assert sp._kokoro is None  # "none" means text-only, full stop


# --- synthesis + playback ----------------------------------------------------

def test_play_kokoro_synthesizes_and_plays(tmp_path, monkeypatch):
    from app.audio.latency import LatencyLog, set_log

    pipeline_cls = _install_fake_kokoro(monkeypatch)

    played = {}

    class _FakeSD:
        def play(self, data, rate, device=None):
            played["rate"] = rate
            played["samples"] = len(data)
            played["device"] = device

        def wait(self):
            played["waited"] = True

        def stop(self):
            pass

    monkeypatch.setitem(sys.modules, "sounddevice", _FakeSD())

    cfg = _cfg(tmp_path, tts_engine="kokoro", kokoro_voice="am_adam",
               tts_rate=180, speaker_device_index=2)
    sp = Speaker(cfg)
    assert sp._kokoro is not None

    log = LatencyLog()
    set_log(log)
    try:
        ok = sp._play_kokoro("hello there")
    finally:
        set_log(None)

    assert ok is True
    assert played["rate"] == 24000            # Kokoro's fixed sample rate
    assert played["samples"] == 4             # two 2-sample chunks concatenated
    assert played["device"] == 2              # honours the selected speaker
    assert played.get("waited") is True       # blocks until playback ends
    assert pipeline_cls.last["voice"] == "am_adam"
    assert abs(pipeline_cls.last["speed"] - 1.0) < 1e-6   # 180 wpm → 1.0x
    assert "TTS synthesis: 1 sample" in log.summary_text()


def test_play_kokoro_returns_false_without_sounddevice(tmp_path, monkeypatch):
    _install_fake_kokoro(monkeypatch)
    monkeypatch.setitem(sys.modules, "sounddevice", None)  # import → ImportError
    sp = Speaker(_cfg(tmp_path, tts_engine="kokoro"))
    assert sp._play_kokoro("hi") is False   # falls back, never raises
    assert sp._kokoro_warned is True


def test_play_kokoro_falls_back_on_synthesis_error(tmp_path, monkeypatch):
    _install_fake_kokoro(monkeypatch)

    class _FakeSD:
        def play(self, *a, **k):
            pass

        def wait(self):
            pass

        def stop(self):
            pass

    monkeypatch.setitem(sys.modules, "sounddevice", _FakeSD())
    sp = Speaker(_cfg(tmp_path, tts_engine="kokoro"))

    def boom(*a, **k):
        raise RuntimeError("model exploded")

    sp._kokoro.synthesize = boom
    assert sp._play_kokoro("hi") is False
    assert sp._kokoro is None  # disabled for the session so it stops retrying


def test_kokoro_speed_maps_from_rate(tmp_path, monkeypatch):
    _install_fake_kokoro(monkeypatch)
    slow = Speaker(_cfg(tmp_path, tts_engine="kokoro", tts_rate=90))
    fast = Speaker(_cfg(tmp_path, tts_engine="kokoro", tts_rate=230))
    assert slow._kokoro_speed() == 0.5   # clamped floor
    assert abs(fast._kokoro_speed() - 230 / 180) < 1e-6


# --- config wiring -----------------------------------------------------------

def test_config_defaults_for_kokoro(monkeypatch):
    for var in ("TTS_ENGINE", "KOKORO_VOICE"):
        monkeypatch.delenv(var, raising=False)
    c = load_config(env_file="/nonexistent/.env")
    assert c.tts_engine == "auto"
    assert c.kokoro_voice == "af_heart"


def test_config_reads_tts_engine_and_voice(monkeypatch):
    monkeypatch.setenv("TTS_ENGINE", "kokoro")
    monkeypatch.setenv("KOKORO_VOICE", "bm_george")
    c = load_config(env_file="/nonexistent/.env")
    assert c.tts_engine == "kokoro"
    assert c.kokoro_voice == "bm_george"
