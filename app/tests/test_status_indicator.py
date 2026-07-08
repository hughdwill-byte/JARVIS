"""Status indicator: state derivation + file read/write (no GUI, no subprocess).

The Tkinter overlay itself needs a display so it isn't unit-tested; the logic
that decides WHICH state to show lives here and is fully testable.
"""

from types import SimpleNamespace

from app.config import Config
from app.ui.status_indicator import StatusIndicator, read_state


def _cfg(tmp_path, **kw):
    base = dict(
        llm_provider="none", vision_provider="none", stt_provider="none",
        tts_provider="none", database_path=tmp_path / "t.db",
        mcp_config_path=tmp_path / "m.json",
    )
    base.update(kw)
    return Config(**base)


def _indicator(tmp_path, *, speaking=False, listening=None):
    cfg = _cfg(tmp_path)
    speaker = SimpleNamespace(is_speaking=speaking)
    vl = None if listening is None else SimpleNamespace(listening=listening)
    return StatusIndicator(cfg, speaker, lambda: vl)


# --- state derivation --------------------------------------------------------

def test_idle_when_nothing_happening(tmp_path):
    assert _indicator(tmp_path).current_state() == "idle"


def test_speaking_wins_over_everything(tmp_path):
    ind = _indicator(tmp_path, speaking=True, listening=True)
    ind.set_thinking(True)
    ind.set_recording(True)
    assert ind.current_state() == "speaking"


def test_thinking_beats_recording_and_armed(tmp_path):
    ind = _indicator(tmp_path, listening=True)
    ind.set_thinking(True)
    ind.set_recording(True)
    assert ind.current_state() == "thinking"


def test_recording_shows_listening(tmp_path):
    ind = _indicator(tmp_path, listening=True)
    ind.set_recording(True)
    assert ind.current_state() == "listening"


def test_armed_when_handsfree_on_but_idle(tmp_path):
    ind = _indicator(tmp_path, listening=True)
    assert ind.current_state() == "armed"


def test_no_voice_loop_is_idle(tmp_path):
    assert _indicator(tmp_path, listening=None).current_state() == "idle"


# --- disabled by default -----------------------------------------------------

def test_start_is_noop_when_overlay_off(tmp_path):
    ind = _indicator(tmp_path)  # status_overlay defaults to False
    ind.start()
    assert ind._proc is None
    assert not ind._started
    # no state file should have been created
    assert not (tmp_path / "status.json").exists() and not ind._state_path.exists()
    ind.close()  # must be safe even though nothing started


# --- file round-trip ---------------------------------------------------------

def test_read_state_round_trip(tmp_path):
    ind = _indicator(tmp_path)
    ind._write("thinking")
    state, ts = read_state(ind._state_path)
    assert state == "thinking"
    assert ts > 0


def test_read_state_missing_file_is_idle(tmp_path):
    assert read_state(tmp_path / "nope.json") == ("idle", 0.0)


def test_read_state_garbage_is_idle(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    assert read_state(p) == ("idle", 0.0)
