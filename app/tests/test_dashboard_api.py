"""Phase 5/7: JARVIS dashboard summary + PWA manifest endpoints."""

from app.assistant import Assistant
from app.config import Config
from app.dashboard.server import create_app


def _cfg(tmp_path, **kw):
    base = dict(
        llm_provider="none", vision_provider="none", stt_provider="none",
        tts_provider="none", wake_word_enabled=False,
        database_path=tmp_path / "t.db", mcp_config_path=tmp_path / "m.json",
    )
    base.update(kw)
    return Config(**base)


def test_dashboard_summary_shape(tmp_path):
    bot = Assistant(_cfg(tmp_path))
    try:
        bot.handle("/task finish the report")
        bot.handle("/remember coffee: flat white")
        s = bot.dashboard_summary()
        assert s["tasks"]["open"] == 1
        assert "finish the report" in s["tasks"]["titles"]
        assert s["memory"]["long_term"] == 1
        assert set(s["devices"]) == {"brain", "camera", "microphone", "voice_output"}
        assert "cost_usd" in s["spend_today"] and "calls" in s["spend_today"]
        assert isinstance(s["attention"], list)
        assert isinstance(s["recent_actions"], list)
    finally:
        bot.close()


def test_api_jarvis_endpoint(tmp_path):
    app = create_app(_cfg(tmp_path), start_voice=False)
    client = app.test_client()
    r = client.get("/api/jarvis")
    assert r.status_code == 200
    data = r.get_json()
    assert "brain" in data and "tasks" in data and "memory" in data
    assert "spend_today" in data


def test_manifest_endpoint_is_installable(tmp_path):
    app = create_app(_cfg(tmp_path), start_voice=False)
    r = app.test_client().get("/manifest.webmanifest")
    assert r.status_code == 200
    m = r.get_json()
    assert m["name"] == "JARVIS"
    assert m["display"] == "standalone"
    assert m["start_url"] == "/"


def test_index_page_links_manifest(tmp_path):
    app = create_app(_cfg(tmp_path), start_voice=False)
    html = app.test_client().get("/").get_data(as_text=True)
    assert 'rel="manifest"' in html
    assert "apple-mobile-web-app-capable" in html
