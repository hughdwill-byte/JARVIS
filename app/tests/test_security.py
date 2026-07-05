"""Phase 4 security: secret redaction + tool-call audit log."""

import logging

from app.assistant import Assistant
from app.brain import security
from app.brain.security import AuditLog, RedactionFilter, redact, set_audit
from app.config import Config


def _cfg(tmp_path, **kw):
    base = dict(
        llm_provider="none", vision_provider="none", stt_provider="none",
        tts_provider="none", database_path=tmp_path / "t.db",
        mcp_config_path=tmp_path / "m.json",
    )
    base.update(kw)
    return Config(**base)


# --- redaction ----------------------------------------------------------------

def test_redacts_anthropic_and_generic_keys():
    assert "sk-ant-" not in redact("key is sk-ant-api03-ABCDEF1234567890abcdef")
    assert "[redacted:anthropic-key]" in redact("sk-ant-api03-ABCDEF1234567890abcdef")
    assert "[redacted:github-token]" in redact("token ghp_ABCDEFGHIJKLMNOP1234567890")
    assert "[redacted:hf-token]" in redact("hf_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345")


def test_redacts_key_value_secrets_keeping_key_name():
    out = redact("ANTHROPIC_API_KEY=sk-supersecretvalue123456 and password: hunter2")
    assert "supersecret" not in out
    assert "hunter2" not in out
    assert "API_KEY" in out or "api_key" in out.lower()  # key name preserved
    assert "[redacted]" in out


def test_redacts_bearer_tokens():
    out = redact("Authorization: Bearer abc123def456ghi789")
    assert "abc123def456" not in out
    assert "Bearer [redacted]" in out


def test_redacts_email_localpart_keeps_domain():
    out = redact("email me at alice.smith@example.com please")
    assert "alice.smith" not in out
    assert "[redacted]@example.com" in out  # domain kept for debuggability


def test_redact_is_safe_on_empty_and_clean_text():
    assert redact("") == ""
    assert redact("nothing sensitive here") == "nothing sensitive here"


def test_redaction_filter_scrubs_log_records():
    filt = RedactionFilter()
    rec = logging.LogRecord("jarvis.test", logging.INFO, __file__, 1,
                            "leaking %s now", ("sk-ant-api03-SECRETKEY1234567890",), None)
    assert filt.filter(rec) is True
    assert "SECRETKEY" not in rec.getMessage()
    assert "[redacted:anthropic-key]" in rec.getMessage()


# --- audit log ----------------------------------------------------------------

def test_audit_records_and_redacts(db):
    audit = AuditLog(db)
    audit.record("run_command", "run: curl -H 'token: sk-ant-api03-SECRET1234567890'",
                 "executed")
    audit.record("gmail__send_email", "gmail app -> send(to=bob@example.com)", "declined")
    text = audit.summary_text()
    assert "SECRET" not in text            # secret scrubbed
    assert "bob" not in text               # email local-part scrubbed
    assert "example.com" in text           # domain kept
    assert "✓" in text and "✗" in text     # executed + declined markers


def test_audit_invalid_outcome_defaults_to_executed(db):
    audit = AuditLog(db)
    audit.record("read_file", "read x", "bogus")
    assert db.recent_audit()[0]["outcome"] == "executed"


def test_audit_empty_is_friendly(db):
    assert "No tool actions recorded" in AuditLog(db).summary_text()


def test_record_tool_call_global_hook_optional():
    set_audit(None)
    security.record_tool_call("x", "y", "executed")  # must not raise when unset


def test_agent_execute_records_audit(tmp_path):
    # Build a real agent with a fake client and confirm each tool call is audited.
    from types import SimpleNamespace

    from app.brain.agent import Agent, AgentTools
    from app.brain.llm_client import LLMClient
    from app.memory.database import Database

    d = tmp_path
    ws = d / "ws"
    ws.mkdir()
    cfg = Config(llm_provider="none", vision_provider="none", stt_provider="none",
                 tts_provider="none", database_path=d / "t.db",
                 mcp_config_path=d / "m.json", agent_allowed_dirs=str(ws))
    (ws / "note.txt").write_text("hello")
    db = Database(cfg.database_path)
    set_audit(AuditLog(db))
    try:
        llm = LLMClient(cfg)

        class FakeClient:
            def __init__(self, responses):
                self._r = list(responses)
                self.messages = self

            def create(self, **kw):
                return self._r.pop(0)

        llm._client = FakeClient([
            SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="list_dir",
                            input={"path": str(ws)}, id="t1")], stop_reason="tool_use"),
            SimpleNamespace(content=[SimpleNamespace(type="text", text="done")],
                            stop_reason="end_turn"),
        ])
        agent = Agent(cfg, llm, AgentTools(cfg), lambda n, d: True)
        agent.run("list my files")
        rows = db.recent_audit()
        assert any(r["tool"] == "list_dir" and r["outcome"] == "executed" for r in rows)
    finally:
        set_audit(None)
        db.close()


# --- assistant wiring ---------------------------------------------------------

def test_audit_command_offline(tmp_path):
    bot = Assistant(_cfg(tmp_path))
    try:
        assert "/audit" in bot.handle("/help").text
        assert "No tool actions recorded" in bot.handle("/audit").text
    finally:
        bot.close()
