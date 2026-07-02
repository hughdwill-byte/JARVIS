"""Agent mode: path sandboxing, approval gating, tool loop, MCP config, wiring."""

import json
from types import SimpleNamespace

import pytest

from app.assistant import Assistant, Reply
from app.brain.agent import Agent, AgentTools, ToolError, describe_action, needs_approval
from app.brain.llm_client import LLMClient
from app.brain.mcp_client import load_mcp_config
from app.config import Config, load_config


@pytest.fixture()
def agent_cfg(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return Config(
        llm_provider="none", vision_provider="none", stt_provider="none",
        tts_provider="none", database_path=tmp_path / "test.db",
        agent_allowed_dirs=str(workspace),
    ), workspace


# --- sandboxing ------------------------------------------------------------

def test_reads_inside_allowed_dir(agent_cfg):
    cfg, ws = agent_cfg
    (ws / "notes.txt").write_text("thermodynamics lecture")
    tools = AgentTools(cfg)
    assert "thermodynamics" in tools.read_file(str(ws / "notes.txt"))
    assert "notes.txt" in tools.list_dir(str(ws))


def test_blocks_paths_outside_allowed_dirs(agent_cfg, tmp_path):
    cfg, ws = agent_cfg
    secret = tmp_path / "outside.txt"  # sibling of workspace, not inside it
    secret.write_text("secret")
    tools = AgentTools(cfg)
    with pytest.raises(ToolError, match="outside the folders"):
        tools.read_file(str(secret))
    with pytest.raises(ToolError, match="outside the folders"):
        tools.write_file(str(secret), "x")


def test_blocks_traversal_escape(agent_cfg):
    cfg, ws = agent_cfg
    tools = AgentTools(cfg)
    with pytest.raises(ToolError, match="outside the folders"):
        tools.read_file(str(ws / ".." / "escape.txt"))


def test_write_and_relative_paths_resolve_to_workspace(agent_cfg):
    cfg, ws = agent_cfg
    tools = AgentTools(cfg)
    assert "Wrote" in tools.write_file("sub/new.txt", "hello")
    assert (ws / "sub" / "new.txt").read_text() == "hello"


def test_run_command_executes_in_workspace(agent_cfg):
    cfg, ws = agent_cfg
    (ws / "a.txt").write_text("x")
    out = AgentTools(cfg).run_command("ls" if not __import__("sys").platform.startswith("win") else "dir")
    assert "a.txt" in out and "[exit 0]" in out


# --- approval gating ----------------------------------------------------------

def test_needs_approval_rules():
    assert needs_approval("write_file")
    assert needs_approval("run_command")
    assert needs_approval("open_app")
    assert not needs_approval("read_file")
    assert not needs_approval("list_dir")
    # MCP tools: state-changing names gated, read-only not
    assert needs_approval("gmail__send_email")
    assert needs_approval("gmail__delete_email")
    assert needs_approval("calendar__create_event")
    assert not needs_approval("gmail__search_emails")
    assert not needs_approval("gmail__read_email")


def test_describe_action_is_human_readable():
    assert "run: ls ~/Downloads" in describe_action("run_command", {"command": "ls ~/Downloads"})
    assert "gmail app" in describe_action("gmail__send_email", {"to": "a@b.c"})


# --- MCP config -------------------------------------------------------------------

def test_load_mcp_config_claude_desktop_shape(tmp_path):
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps({"mcpServers": {
        "gmail": {"command": "npx", "args": ["-y", "some-server"], "env": {"K": "v"}},
    }}))
    servers = load_mcp_config(p)
    assert servers["gmail"]["command"] == "npx"
    assert servers["gmail"]["env"] == {"K": "v"}


def test_load_mcp_config_errors(tmp_path):
    assert load_mcp_config(tmp_path / "missing.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_mcp_config(bad)
    no_cmd = tmp_path / "nocmd.json"
    no_cmd.write_text(json.dumps({"mcpServers": {"x": {"args": []}}}))
    with pytest.raises(ValueError, match="command"):
        load_mcp_config(no_cmd)


# --- the tool loop (with a fake API client) ---------------------------------------

def _text(t):
    return SimpleNamespace(type="text", text=t)


def _tool_use(name, args, id="tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=id)


class FakeClient:
    """Stands in for the Anthropic client: returns scripted responses in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = self  # so client.messages.create(...) works

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def _agent_with(cfg, responses, approve=lambda name, desc: True):
    llm = LLMClient(cfg)
    llm._client = FakeClient(responses)  # inject the fake; llm.available becomes True
    return Agent(cfg, llm, AgentTools(cfg), approve), llm._client


def test_conversation_without_tools_is_plain_chat(agent_cfg):
    cfg, _ws = agent_cfg
    agent, client = _agent_with(cfg, [
        SimpleNamespace(content=[_text("Entropy measures disorder.")], stop_reason="end_turn"),
    ])
    reply, actions = agent.run_conversation("explain entropy")
    assert reply == "Entropy measures disorder."
    assert actions == []
    assert "tools" in client.calls[0]  # tools offered, just not used


def test_conversation_uses_tool_then_answers(agent_cfg):
    cfg, ws = agent_cfg
    (ws / "essay.txt").write_text("draft")
    agent, client = _agent_with(cfg, [
        SimpleNamespace(content=[_tool_use("list_dir", {"path": str(ws)})],
                        stop_reason="tool_use"),
        SimpleNamespace(content=[_text("You have one file: essay.txt.")],
                        stop_reason="end_turn"),
    ])
    reply, actions = agent.run_conversation("what's in my workspace?")
    assert "essay.txt" in reply
    assert len(actions) == 1
    # the second call must include the tool result for the first
    second = client.calls[1]["messages"]
    tool_results = [
        part for m in second if isinstance(m.get("content"), list)
        for part in m["content"]
        if isinstance(part, dict) and part.get("type") == "tool_result"
    ]
    assert tool_results and "essay.txt" in tool_results[0]["content"]
    # and escalates to the smart model once acting
    assert client.calls[1]["model"] == cfg.llm_model_smart


def test_declined_action_is_reported_not_executed(agent_cfg):
    cfg, ws = agent_cfg
    agent, _client = _agent_with(cfg, [
        SimpleNamespace(content=[_tool_use("write_file",
                                           {"path": str(ws / "x.txt"), "content": "hi"})],
                        stop_reason="tool_use"),
        SimpleNamespace(content=[_text("Okay, I won't write the file.")],
                        stop_reason="end_turn"),
    ], approve=lambda name, desc: False)
    reply, actions = agent.run_conversation("make a file")
    assert not (ws / "x.txt").exists()
    assert any("(declined)" in a for a in actions)


def test_web_search_tool_offered_when_enabled(agent_cfg):
    cfg, _ws = agent_cfg
    cfg.web_search_enabled = True
    agent, client = _agent_with(cfg, [
        SimpleNamespace(content=[_text("ok")], stop_reason="end_turn"),
    ])
    agent.run_conversation("who won this morning?")
    names = [t.get("name") for t in client.calls[0]["tools"]]
    assert "web_search" in names

    cfg.web_search_enabled = False
    agent2, client2 = _agent_with(cfg, [
        SimpleNamespace(content=[_text("ok")], stop_reason="end_turn"),
    ])
    agent2.run_conversation("who won this morning?")
    assert "web_search" not in [t.get("name") for t in client2.calls[0]["tools"]]


def test_pause_turn_continues_loop(agent_cfg):
    cfg, _ws = agent_cfg
    paused = SimpleNamespace(content=[_text("searching…")], stop_reason="pause_turn")
    done = SimpleNamespace(content=[_text("The score was 2-1.")], stop_reason="end_turn")
    agent, client = _agent_with(cfg, [paused, done])
    reply, actions = agent.run_conversation("this morning's score?")
    assert reply == "The score was 2-1."
    assert len(client.calls) == 2  # continued after the pause


def test_reply_spoken_excludes_action_log():
    r = Reply("answer\n\nActions taken:\n  - stuff", speak_text="answer")
    assert r.spoken == "answer"
    assert Reply("plain").spoken == "plain"


# --- assistant wiring ------------------------------------------------------------

def test_agent_command_offline_and_disabled(cfg):
    bot = Assistant(cfg)
    try:
        assert "task" in bot.handle("/agent").text.lower()  # usage hint
        assert "AI Brain" in bot.handle("/agent do something").text
        bot.cfg.agent_enabled = False
        assert "turned off" in bot.handle("/agent do something").text
        assert "No apps configured" in bot.handle("/apps").text
    finally:
        bot.close()


def test_agent_config_defaults(monkeypatch):
    for var in ("AGENT_ENABLED", "AGENT_AUTO_APPROVE", "AGENT_ALLOWED_DIRS", "AGENT_MAX_STEPS"):
        monkeypatch.delenv(var, raising=False)
    c = load_config(env_file="/nonexistent/.env")
    assert c.agent_enabled is True
    assert c.agent_auto_approve is False  # safe default: always ask
    assert c.agent_allowed_dirs == "~"
    assert c.agent_max_steps == 15
