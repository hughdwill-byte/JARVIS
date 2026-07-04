"""Phase 2 voice: Piper TTS provider + latency instrumentation.

No audio hardware or piper binary needed — we test the decision logic and
fallback behaviour, which is where the bugs would actually be.
"""

from pathlib import Path

from app.assistant import Assistant
from app.audio.latency import LatencyLog, record, set_log
from app.audio.text_to_speech import Speaker
from app.config import Config


def _cfg(tmp_path, **kw):
    base = dict(
        llm_provider="none", vision_provider="none", stt_provider="none",
        database_path=tmp_path / "t.db", mcp_config_path=tmp_path / "m.json",
    )
    base.update(kw)
    return Config(**base)


# --- latency log --------------------------------------------------------------

def test_latency_log_records_and_summarises():
    log = LatencyLog()
    log.record("stt", 1200)
    log.record("stt", 800)
    log.record("tts", 300)
    text = log.summary_text()
    assert "Speech-to-text: 2 sample(s)" in text
    assert "TTS synthesis: 1 sample(s)" in text
    assert "avg 1.00s" in text  # (1200+800)/2 = 1000ms


def test_latency_log_ignores_unknown_stage_and_empty():
    log = LatencyLog()
    log.record("bogus", 999)
    assert "no samples yet" in log.summary_text()


def test_latency_global_hook_is_optional():
    set_log(None)
    record("stt", 500)  # must not raise when no log is set
    log = LatencyLog()
    set_log(log)
    record("stt", 500)
    assert "1 sample" in log.summary_text()
    set_log(None)


def test_latency_ring_buffer_caps_samples():
    log = LatencyLog(keep=3)
    for ms in (100, 200, 300, 400):
        log.record("tts", ms)
    # only the last 3 survive; min should be 200, not 100
    assert "min 0.20s" in log.summary_text()


# --- piper provider selection & fallback --------------------------------------

def test_pyttsx3_provider_does_not_enable_piper(tmp_path):
    sp = Speaker(_cfg(tmp_path, tts_provider="pyttsx3"))
    assert sp._piper is None


def test_piper_provider_without_binary_is_no_worse_than_pyttsx3(tmp_path):
    # piper binary almost certainly absent here -> _piper is None. Choosing
    # piper must never leave TTS *more* disabled than plain pyttsx3 would:
    # if the OS voice is usable, piper falls back to it (never goes mute); if
    # this box has no OS voice at all, both are equally text-only.
    piper = Speaker(_cfg(tmp_path, tts_provider="piper", piper_voice_model="/nope/x.onnx"))
    pyttsx = Speaker(_cfg(tmp_path, tts_provider="pyttsx3"))
    assert piper._piper is None
    assert piper.available == pyttsx.available


def test_piper_play_returns_false_when_model_missing(tmp_path):
    cfg = _cfg(tmp_path, tts_provider="piper", piper_voice_model="/does/not/exist.onnx")
    sp = Speaker(cfg)
    sp._piper = "/usr/bin/piper"  # pretend the binary exists
    assert sp._play_piper("hello") is False  # missing model -> fall back
    assert sp._piper_warned is True          # warned once, won't spam


def test_piper_command_is_built_correctly(tmp_path, monkeypatch):
    voice = tmp_path / "voice.onnx"
    voice.write_bytes(b"fake-onnx")
    cfg = _cfg(tmp_path, tts_provider="piper", piper_voice_model=str(voice),
               piper_speaker=3)
    sp = Speaker(cfg)
    sp._piper = "piper"
    captured = {}

    class _FakeProc:
        returncode = 0

        def communicate(self, input=None, timeout=None):
            captured["input"] = input
            return (b"", b"")

    def fake_popen(cmd, **kw):
        captured["cmd"] = cmd
        # piper "writes" the wav so playback stage sees a non-empty file
        out = cmd[cmd.index("--output_file") + 1]
        Path(out).write_bytes(b"RIFFfakewavdata")
        return _FakeProc()

    played = {}

    class _FakeSD:
        def play(self, data, rate, device=None):
            played["rate"] = rate

        def wait(self):
            played["waited"] = True

        def stop(self):
            pass

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", _FakeSD())
    monkeypatch.setitem(__import__("sys").modules, "soundfile",
                        type("sf", (), {"read": staticmethod(
                            lambda p, dtype=None: ([0.0, 0.1], 22050))})())

    log = LatencyLog()
    set_log(log)
    try:
        ok = sp._play_piper("hello there")
    finally:
        set_log(None)

    assert ok is True
    assert captured["cmd"][0] == "piper"
    assert "--model" in captured["cmd"] and str(voice) in captured["cmd"]
    assert "--speaker" in captured["cmd"] and "3" in captured["cmd"]
    assert captured["input"] == b"hello there"
    assert played.get("waited") is True
    assert "TTS synthesis: 1 sample" in log.summary_text()  # latency recorded


# --- assistant wiring ---------------------------------------------------------

def test_voicestats_command_offline(tmp_path):
    bot = Assistant(_cfg(tmp_path, tts_provider="none"))
    try:
        out = bot.handle("/voicestats").text
        assert "Voice latency" in out
        # record a sample through the live global hook, then see it surface
        record("tts", 250)
        assert "TTS synthesis: 1 sample" in bot.handle("/voicestats").text
    finally:
        bot.close()
