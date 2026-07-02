"""Settings app: .env editing, masking, API round-trips, hot-restart."""

import pytest

from app.dashboard.settings import (
    SETTINGS_SCHEMA,
    mask_secret,
    read_env_values,
    update_env_file,
)

flask = pytest.importorskip("flask")
from app.dashboard.server import create_app  # noqa: E402


@pytest.fixture()
def env_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text(
        "# my comment stays\n"
        "ANTHROPIC_API_KEY=sk-ant-original-key-1234\n"
        "TTS_RATE=180\n"
        "UNRELATED=keepme\n",
        encoding="utf-8",
    )
    return f


def test_update_env_preserves_comments_and_unknown_lines(env_file):
    update_env_file({"TTS_RATE": "200", "CAMERA_INDEX": "1"}, env_file)
    content = env_file.read_text()
    assert "# my comment stays" in content
    assert "UNRELATED=keepme" in content
    assert "TTS_RATE=200" in content
    assert "CAMERA_INDEX=1" in content  # appended, wasn't there before


def test_update_env_rejects_unknown_keys(env_file):
    written = update_env_file({"EVIL_KEY": "x", "TTS_RATE": "190"}, env_file)
    assert written == ["TTS_RATE"]
    assert "EVIL_KEY" not in env_file.read_text()


def test_masked_key_never_saved(env_file):
    update_env_file({"ANTHROPIC_API_KEY": "••••1234"}, env_file)
    assert "sk-ant-original-key-1234" in env_file.read_text()  # untouched
    update_env_file({"ANTHROPIC_API_KEY": "sk-ant-new-key-5678"}, env_file)
    assert "sk-ant-new-key-5678" in env_file.read_text()


def test_mask_secret():
    assert mask_secret("") == ""
    assert mask_secret("sk-ant-abcdef123456").endswith("3456")
    assert mask_secret("sk-ant-abcdef123456").startswith("•")
    assert "abcdef" not in mask_secret("sk-ant-abcdef123456")


def test_read_env_values(env_file):
    values = read_env_values(env_file)
    assert values["TTS_RATE"] == "180"
    assert "UNRELATED" not in values  # only schema keys exposed to the UI


def test_schema_covers_essentials():
    keys = {i["key"] for s in SETTINGS_SCHEMA for i in s["items"]}
    for essential in ("ANTHROPIC_API_KEY", "MIC_DEVICE_INDEX", "SPEAKER_DEVICE_INDEX",
                      "CAMERA_INDEX", "WAKE_WORD_ENABLED", "TTS_RATE"):
        assert essential in keys


@pytest.fixture()
def client(cfg, tmp_path):
    app = create_app(cfg, env_path=tmp_path / ".env", start_voice=False)
    app.config["TESTING"] = True
    return app.test_client()


def test_settings_api_roundtrip(client, tmp_path):
    data = client.get("/api/settings").get_json()
    assert data["schema"] and "values" in data and "audio" in data

    resp = client.post("/api/settings", json={"TTS_RATE": "170", "DEBUG": "true"}).get_json()
    assert resp["ok"] and set(resp["written"]) == {"TTS_RATE", "DEBUG"}
    content = (tmp_path / ".env").read_text()
    assert "TTS_RATE=170" in content and "DEBUG=true" in content


def test_settings_api_masks_key(client, tmp_path):
    client.post("/api/settings", json={"ANTHROPIC_API_KEY": "sk-ant-secret-abcd9999"})
    values = client.get("/api/settings").get_json()["values"]
    assert "secret" not in values["ANTHROPIC_API_KEY"]
    assert values["ANTHROPIC_API_KEY"].endswith("9999")


def test_favourite_voices_roundtrip(client, tmp_path):
    """Favourites persist via the settings API even though they're not a schema field."""
    resp = client.post("/api/settings",
                       json={"TTS_FAVOURITE_VOICES": "com.apple.voice.Jamie,com.apple.voice.Daniel"})
    assert resp.get_json()["ok"]
    assert "TTS_FAVOURITE_VOICES=com.apple.voice.Jamie,com.apple.voice.Daniel" in \
        (tmp_path / ".env").read_text()
    values = client.get("/api/settings").get_json()["values"]
    assert values["TTS_FAVOURITE_VOICES"] == "com.apple.voice.Jamie,com.apple.voice.Daniel"


def test_restart_endpoint(client):
    assert client.post("/api/restart").get_json()["ok"]
    # The app still answers after the swap
    state = client.get("/api/state").get_json()
    assert "llm_available" in state


def test_device_test_endpoints_degrade_gracefully(client):
    """No devices in CI -> ok:false with an actionable message, never a 500."""
    for kind in ("speaker", "mic", "camera", "llm"):
        resp = client.post(f"/api/test/{kind}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is False
        assert len(data["message"]) > 10  # says WHAT to fix
