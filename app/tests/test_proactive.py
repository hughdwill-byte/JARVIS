"""Phase 6: proactive monitor, do-not-disturb, notification budget."""

from datetime import datetime, timedelta, timezone

from app.assistant import Assistant
from app.config import Config
from app.memory.database import Database
from app.tools.proactive import ProactiveMonitor


def _cfg(tmp_path, **kw):
    base = dict(
        llm_provider="none", vision_provider="none", stt_provider="none",
        tts_provider="none", database_path=tmp_path / "t.db",
        mcp_config_path=tmp_path / "m.json",
    )
    base.update(kw)
    return Config(**base)


def _age_task(db: Database, title: str, days_old: int) -> None:
    db.add_task(title)
    old = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat(timespec="seconds")
    # backdate created_at so it looks stale
    db._execute("UPDATE tasks SET created_at = ? WHERE title = ?", (old, title))


def test_flags_stale_tasks_only(tmp_path):
    cfg = _cfg(tmp_path, stale_task_days=7)
    db = Database(cfg.database_path)
    _age_task(db, "old lab report", 10)
    db.add_task("fresh task")  # today -> not stale
    try:
        msgs = ProactiveMonitor(cfg, db).checkins(force=True)
        assert len(msgs) == 1
        assert "old lab report" in msgs[0]
        assert "fresh task" not in msgs[0]
    finally:
        db.close()


def test_do_not_disturb_silences_automatic_but_not_checkin(tmp_path):
    cfg = _cfg(tmp_path, stale_task_days=1, do_not_disturb=True)
    db = Database(cfg.database_path)
    _age_task(db, "lingering task", 5)
    try:
        mon = ProactiveMonitor(cfg, db)
        assert mon.checkins(force=False) == []          # DND silences automatic
        assert "lingering task" in mon.summary_text()   # /checkin still answers
    finally:
        db.close()


def test_disabled_silences_automatic(tmp_path):
    cfg = _cfg(tmp_path, stale_task_days=1, proactive_enabled=False)
    db = Database(cfg.database_path)
    _age_task(db, "task", 5)
    try:
        assert ProactiveMonitor(cfg, db).checkins(force=False) == []
    finally:
        db.close()


def test_throttle_blocks_second_automatic_run(tmp_path):
    cfg = _cfg(tmp_path, stale_task_days=1, proactive_interval_s=3600)
    db = Database(cfg.database_path)
    _age_task(db, "task", 5)
    try:
        mon = ProactiveMonitor(cfg, db)
        assert mon.checkins(force=False)        # first run fires
        assert mon.checkins(force=False) == []  # throttled within the hour
    finally:
        db.close()


def test_budget_caps_automatic_messages(tmp_path):
    # 2 stale-task-groups would each be one message; but stale tasks collapse to
    # one message, so test the budget cap by lowering it to 0.
    cfg = _cfg(tmp_path, stale_task_days=1, notify_budget=0)
    db = Database(cfg.database_path)
    _age_task(db, "task", 5)
    try:
        assert ProactiveMonitor(cfg, db).checkins(force=False) == []  # budget 0
    finally:
        db.close()


def test_summary_text_all_quiet(tmp_path):
    cfg = _cfg(tmp_path)
    db = Database(cfg.database_path)
    try:
        assert "All quiet" in ProactiveMonitor(cfg, db).summary_text()
    finally:
        db.close()


def test_internal_preference_keys_hidden_from_user(tmp_path):
    """reply_style / proactive_last_run must not appear as user 'memories',
    in the LLM context, or the vault export."""
    bot = Assistant(_cfg(tmp_path))
    try:
        bot.handle("/brief")                 # writes reply_style
        bot.handle("/checkin")               # writes proactive_last_run
        bot.handle("/remember coffee: flat white")
        mem = bot.handle("/memories").text
        assert "coffee" in mem
        assert "reply_style" not in mem and "proactive_last_run" not in mem
        assert all("proactive_last_run" not in c for c in bot.prefs.as_context())
    finally:
        bot.close()


def test_checkin_and_dnd_commands(tmp_path, monkeypatch):
    # Don't let /dnd write to the real project .env during tests.
    monkeypatch.setattr("app.dashboard.settings.update_env_file",
                        lambda *a, **k: [])
    bot = Assistant(_cfg(tmp_path))
    try:
        assert "/checkin" in bot.handle("/help").text
        assert "quiet" in bot.handle("/checkin").text.lower()
        on = bot.handle("/dnd").text
        assert "Do Not Disturb on" in on and bot.cfg.do_not_disturb is True
        off = bot.handle("/dnd").text
        assert "Do Not Disturb off" in off and bot.cfg.do_not_disturb is False
    finally:
        bot.close()
