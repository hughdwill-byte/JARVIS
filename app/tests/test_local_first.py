"""Local-first brain: Ollama client, routing, usage tracking, briefing, export."""

import io
import json
import time

import pytest

from app.assistant import Assistant
from app.brain.llm_client import looks_unanswered, needs_current_info
from app.brain.ollama_client import LocalFirstClient, OllamaClient, _strip_think
from app.brain.usage import UsageTracker, estimate_cost
from app.config import Config
from app.tools.briefing import build_briefing
from app.tools.vault_export import export_vault


@pytest.fixture()
def lf_cfg(tmp_path):
    """local_first config WITH an API key (fake; no network calls made)."""
    return Config(
        llm_provider="local_first", anthropic_api_key="sk-ant-test",
        vision_provider="none", stt_provider="none", tts_provider="none",
        database_path=tmp_path / "t.db", mcp_config_path=tmp_path / "mcp.json",
    )


def _force_ollama(client: OllamaClient, up: bool) -> None:
    client._ping_ok = up
    client._ping_at = time.monotonic()


# --- routing -----------------------------------------------------------------

def test_local_first_routes_easy_chat_to_local(lf_cfg):
    lf = LocalFirstClient(lf_cfg)
    _force_ollama(lf.ollama, True)
    assert lf.api.available  # fake key initialises the SDK client
    assert lf.pick_model("hi") == lf_cfg.ollama_model
    assert lf.pick_model("what's a good cat name?") == lf_cfg.ollama_model


def test_local_first_routes_hard_and_deep_to_cloud(lf_cfg):
    lf = LocalFirstClient(lf_cfg)
    _force_ollama(lf.ollama, True)
    assert lf.pick_model("debug this crash for me") == lf_cfg.llm_model_smart
    assert lf.pick_model("hi", force_smart=True) == lf_cfg.llm_model_smart
    assert lf.pick_model("write an in-depth report on X") == lf_cfg.llm_model_deep


def test_local_first_falls_back_to_cloud_when_ollama_down(lf_cfg):
    lf = LocalFirstClient(lf_cfg)
    _force_ollama(lf.ollama, False)
    assert lf.pick_model("hi") == lf_cfg.llm_model_fast  # cloud cheap tier


def test_local_first_stays_local_without_api_key(tmp_path):
    cfg = Config(llm_provider="local_first", anthropic_api_key="",
                 database_path=tmp_path / "t.db", mcp_config_path=tmp_path / "m.json")
    lf = LocalFirstClient(cfg)
    _force_ollama(lf.ollama, True)
    assert not lf.api.available
    # even "hard" requests stay local: no key = no cloud
    assert lf.pick_model("debug this crash for me") == cfg.ollama_model


def test_local_first_chat_dispatch(lf_cfg):
    lf = LocalFirstClient(lf_cfg)
    _force_ollama(lf.ollama, True)
    lf.ollama.chat = lambda *a, **k: "LOCAL"
    lf.api.chat = lambda *a, **k: "CLOUD"
    assert lf.chat("hi") == "LOCAL"
    assert lf.chat("debug this crash for me") == "CLOUD"
    assert lf.chat("hi", force_smart=True) == "CLOUD"


def test_local_first_raw_is_none_so_chat_never_rides_cloud_tool_loop(lf_cfg):
    assert LocalFirstClient(lf_cfg).raw is None


# --- current-info escalation (get an answer no matter which brain) ------------

def test_needs_current_info_detection():
    assert needs_current_info("who played in the world cup last night")
    assert needs_current_info("what's the weather today")
    assert needs_current_info("latest news on the election")
    assert needs_current_info("what's the current price of a Pi 5")
    assert needs_current_info("who won the match")
    assert not needs_current_info("explain how photosynthesis works")
    assert not needs_current_info("write a poem about the sea")


def test_looks_unanswered_detection():
    assert looks_unanswered("I don't have access to real-time information.")
    assert looks_unanswered("As of my knowledge cutoff, I can't say.")
    assert looks_unanswered("I cannot browse the internet to check the latest scores.")
    assert not looks_unanswered("City beat United 2-1 at the death.")
    assert not looks_unanswered("")


def test_current_info_question_routes_straight_to_cloud(lf_cfg):
    lf = LocalFirstClient(lf_cfg)
    _force_ollama(lf.ollama, True)
    calls = {"local": 0, "cloud": 0}
    lf.ollama.chat = lambda *a, **k: (calls.__setitem__("local", calls["local"] + 1), "LOCAL")[1]
    lf.api.chat = lambda *a, **k: (calls.__setitem__("cloud", calls["cloud"] + 1), "CLOUD web result")[1]
    out = lf.chat("who played in the world cup last night")
    assert out == "CLOUD web result"
    assert calls["cloud"] == 1 and calls["local"] == 0  # never wasted a local call


def test_local_punt_escalates_to_cloud(lf_cfg):
    lf = LocalFirstClient(lf_cfg)
    _force_ollama(lf.ollama, True)
    seen = {}
    lf.ollama.chat = lambda *a, **k: "I don't have access to real-time information."
    def cloud(user_text, history=None, context_block="", force_smart=False, max_tokens=None):
        seen["force_smart"] = force_smart
        return "United won 3-0."
    lf.api.chat = cloud
    # a phrasing with no current-info keywords, so it hits the local model first;
    # the local model punts, which should trigger the cloud escalation
    out = lf.chat("how are the reds getting on")
    assert out == "United won 3-0."
    assert seen["force_smart"] is True  # escalation uses the best cloud shot


def test_good_local_answer_is_not_escalated(lf_cfg):
    lf = LocalFirstClient(lf_cfg)
    _force_ollama(lf.ollama, True)
    cloud_calls = {"n": 0}
    lf.ollama.chat = lambda *a, **k: "Photosynthesis converts light into chemical energy."
    lf.api.chat = lambda *a, **k: (cloud_calls.__setitem__("n", cloud_calls["n"] + 1), "X")[1]
    out = lf.chat("explain photosynthesis")
    assert "Photosynthesis" in out
    assert cloud_calls["n"] == 0  # stayed local & free, no needless cloud call


def test_no_escalation_without_api_key(tmp_path):
    cfg = Config(llm_provider="local_first", anthropic_api_key="",
                 database_path=tmp_path / "t.db", mcp_config_path=tmp_path / "m.json")
    lf = LocalFirstClient(cfg)
    _force_ollama(lf.ollama, True)
    lf.ollama.chat = lambda *a, **k: "I don't have access to real-time information."
    # no key -> can't escalate; returns the honest local reply rather than crashing
    out = lf.chat("who won last night")
    assert "real-time" in out


# --- Ollama client ------------------------------------------------------------

class _FakeResp:
    def __init__(self, payload: dict):
        self.status = 200
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_ollama_chat_parses_reply_and_strips_think(lf_cfg, monkeypatch):
    client = OllamaClient(lf_cfg)
    _force_ollama(client, True)
    fake = _FakeResp({"message": {"content": "<think>hmm</think>Hello there."},
                      "prompt_eval_count": 10, "eval_count": 5})
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=0: fake)
    assert client.chat("hi") == "Hello there."


def test_ollama_unreachable_gives_setup_help(lf_cfg):
    client = OllamaClient(lf_cfg)
    _force_ollama(client, False)
    reply = client.chat("hi")
    assert "ollama" in reply.lower() and "ollama pull" in reply


def test_strip_think_handles_unclosed_block():
    assert _strip_think("<think>never ends") == ""
    assert _strip_think("a<think>x</think>b<think>y</think>c") == "abc"
    assert _strip_think("plain") == "plain"


# --- usage tracking -----------------------------------------------------------

def test_estimate_cost_by_model():
    assert estimate_cost("claude-haiku-4-5", 1_000_000, 0) == pytest.approx(1.0)
    assert estimate_cost("claude-sonnet-5", 0, 1_000_000) == pytest.approx(15.0)
    assert estimate_cost("claude-opus-4-8", 1_000_000, 1_000_000) == pytest.approx(30.0)
    assert estimate_cost("qwen3:8b", 1_000_000, 1_000_000) == 0.0


def test_usage_tracker_records_and_summarises(db):
    tracker = UsageTracker(db)
    tracker.record("api", "claude-haiku-4-5", 1000, 500, 800)
    tracker.record("ollama", "qwen3:8b", 2000, 900, 1500)
    text = tracker.summary_text()
    assert "claude-haiku-4-5" in text and "qwen3:8b" in text
    assert "free (local)" in text


# --- briefing -------------------------------------------------------------------

def test_briefing_includes_tasks_reminders_notes(db):
    db.add_task("finish lab report", due="friday")
    db.add_task("email tutor")
    db.add_reminder("2099-01-01T09:00:00+00:00", "stretch")
    db.add_note("thermo exam covers chapters 3-5")
    text = build_briefing(db)
    assert "Good morning" in text
    assert "finish lab report" in text and "due friday" in text
    assert "stretch" in text
    assert "thermo exam" in text


def test_briefing_empty_state_is_friendly(db):
    text = build_briefing(db)
    assert "Good morning" in text and "No open tasks" in text


# --- vault export -----------------------------------------------------------------

def test_export_writes_obsidian_markdown(db, tmp_path):
    db.add_note("buy resistors")
    db.set_preference("coffee", "flat white, no sugar")
    db.add_task("solder the board", due="monday")
    tid = db.add_task("order PCB")
    db.complete_task(tid)
    msg = export_vault(db, tmp_path / "vault")
    out = tmp_path / "vault" / "JARVIS"
    assert "Exported" in msg
    assert "buy resistors" in (out / "Notes.md").read_text()
    assert "flat white" in (out / "Memories.md").read_text()
    tasks_md = (out / "Tasks.md").read_text()
    assert "- [ ] solder the board (due monday)" in tasks_md
    assert "- [x] order PCB" in tasks_md


# --- assistant wiring (fully offline) ----------------------------------------------

def test_new_commands_work_offline(cfg):
    bot = Assistant(cfg)
    try:
        assert "Good morning" in bot.handle("/briefing").text
        assert "Good morning" in bot.handle("good morning").text  # phrase route
        assert "usage" in bot.handle("/usage").text.lower()
        assert "Brief mode on" in bot.handle("/brief").text
        assert bot.db.get_preference("reply_style") == "brief"
        assert "Detailed mode on" in bot.handle("/detailed").text
        assert "Exported" in bot.handle("/export").text
    finally:
        bot.close()


def test_reply_style_line_injection(cfg):
    bot = Assistant(cfg)
    try:
        assert bot._reply_style_line() == ""
        bot.handle("/brief")
        assert "BRIEF MODE" in bot._reply_style_line()
    finally:
        bot.close()
