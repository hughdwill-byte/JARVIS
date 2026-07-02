"""Agent mode: path sandboxing, approval gating, MCP config parsing, wiring."""

import json

import pytest

from app.assistant import Assistant
from app.brain.agent import AgentTools, ToolError, describe_action, needs_approval
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


# --- assistant wiring ------------------------------------------------------------

def test_agent_command_offline_and_disabled(cfg):
    bot = Assistant(cfg)
    try:
        assert "task" in bot.handle("/agent").text.lower()  # usage hint
        assert "API key" in bot.handle("/agent do something").text
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
