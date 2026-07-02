"""Brain backends: factory, Claude Code CLI wrapper, hybrid routing."""

import json
from types import SimpleNamespace

from app.brain import llm_client as mod
from app.brain.llm_client import (
    CLAUDE_CODE_MISSING,
    ClaudeCodeClient,
    HybridClient,
    LLMClient,
    create_llm_client,
)
from app.config import Config


def _cfg(provider, key="", **kw):
    return Config(llm_provider=provider, anthropic_api_key=key,
                  stt_provider="none", tts_provider="none", vision_provider="none", **kw)


# --- factory ---------------------------------------------------------------

def test_factory_picks_backend():
    assert isinstance(create_llm_client(_cfg("anthropic")), LLMClient)
    assert isinstance(create_llm_client(_cfg("claude_code")), ClaudeCodeClient)
    assert isinstance(create_llm_client(_cfg("hybrid")), HybridClient)
    none_client = create_llm_client(_cfg("none", key="sk-test"))
    assert isinstance(none_client, LLMClient) and not none_client.available


def test_llm_available_includes_hybrid():
    assert _cfg("hybrid", key="sk-test").llm_available
    assert not _cfg("claude_code", key="sk-test").llm_available  # CC ignores the key


# --- Claude Code backend --------------------------------------------------------

def test_cc_unavailable_without_cli(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    cc = ClaudeCodeClient(_cfg("claude_code"))
    assert not cc.available
    assert "npm install" in cc.chat("hello")
    assert cc.raw is None


def test_cc_chat_runs_cli_and_strips_api_key(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stderr="",
                               stdout=json.dumps({"result": "Hello there.", "is_error": False}))

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    cc = ClaudeCodeClient(_cfg("claude_code"))
    reply = cc.chat("hi", history=[{"role": "user", "content": "earlier"},
                                   {"role": "assistant", "content": "yes?"}])
    assert reply == "Hello there."
    assert "ANTHROPIC_API_KEY" not in captured["env"]  # bill the subscription, not the API
    assert "--model" in captured["cmd"] and "-p" in captured["cmd"]
    assert "earlier" in captured["cmd"][2]  # history serialised into the prompt


def test_cc_login_error_gives_instructions(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **k: SimpleNamespace(
        returncode=1, stdout="", stderr="Invalid API key · Please run /login"))
    cc = ClaudeCodeClient(_cfg("claude_code"))
    assert "sign in" in cc.chat("hi")


def test_cc_agent_task_readonly_unless_auto_approve(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/claude")
    calls = []
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **k: (
        calls.append(cmd),
        SimpleNamespace(returncode=0, stderr="",
                        stdout=json.dumps({"result": "done", "is_error": False})))[1])
    cc = ClaudeCodeClient(_cfg("claude_code"))
    cc.agent_task("list stuff", str(tmp_path), auto_approve=False)
    ro = calls[0][calls[0].index("--allowedTools") + 1]
    assert "Write" not in ro and "Bash" not in ro
    cc.agent_task("fix stuff", str(tmp_path), auto_approve=True)
    rw = calls[1][calls[1].index("--allowedTools") + 1]
    assert "Write" in rw and "--permission-mode" in calls[1]


# --- hybrid routing -----------------------------------------------------------------

def _fake(name, available=True):
    return SimpleNamespace(
        available=available,
        chat=lambda *a, **k: name,
        analyze_image=lambda *a, **k: name,
        analyze_image_file=lambda *a, **k: name,
        raw=object() if name == "api" else None,
    )


def test_hybrid_routes_big_tasks_to_subscription():
    h = HybridClient(_cfg("hybrid"))
    h.api, h.cc = _fake("api"), _fake("cc")
    assert h.chat("quick question") == "api"
    assert h.chat("summarise this", force_smart=True) == "cc"
    assert h.analyze_image_file("/tmp/x.jpg", "describe") == "cc"


def test_hybrid_falls_back_when_one_side_missing():
    h = HybridClient(_cfg("hybrid"))
    h.api, h.cc = _fake("api"), _fake("cc", available=False)
    assert h.chat("summarise this", force_smart=True) == "api"  # CC missing -> API
    h.api, h.cc = _fake("api", available=False), _fake("cc")
    assert h.chat("quick question") == "cc"  # no key -> subscription handles chat too
    assert h.available
