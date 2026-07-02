"""Config loading: defaults, env overrides, derived paths."""

from app.config import Config, load_config


def test_defaults_boot_without_env(monkeypatch):
    for var in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "CAMERA_INDEX", "DEBUG",
                "DATABASE_PATH", "DASHBOARD_PORT"):
        monkeypatch.delenv(var, raising=False)
    cfg = load_config(env_file="/nonexistent/.env")
    assert cfg.llm_provider == "anthropic"
    assert cfg.camera_index == 0
    assert cfg.dashboard_port == 8321
    assert cfg.debug is False
    assert cfg.llm_available is False  # no key -> offline mode, not a crash


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("CAMERA_INDEX", "2")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("LLM_MAX_TOKENS", "512")
    monkeypatch.setenv("MIC_DEVICE_INDEX", "3")
    cfg = load_config(env_file="/nonexistent/.env")
    assert cfg.camera_index == 2
    assert cfg.debug is True
    assert cfg.llm_max_tokens == 512
    assert cfg.mic_device_index == 3


def test_bad_int_falls_back(monkeypatch):
    monkeypatch.setenv("CAMERA_INDEX", "not-a-number")
    cfg = load_config(env_file="/nonexistent/.env")
    assert cfg.camera_index == 0


def test_llm_available_requires_key():
    assert Config(llm_provider="anthropic", anthropic_api_key="sk-test").llm_available
    assert not Config(llm_provider="anthropic", anthropic_api_key="").llm_available
    assert not Config(llm_provider="none", anthropic_api_key="sk-test").llm_available


def test_derived_dirs(tmp_path):
    cfg = Config(database_path=tmp_path / "data" / "jarvis.db")
    cfg.ensure_dirs()
    assert cfg.snapshots_dir.is_dir()
    assert cfg.logs_dir.is_dir()
    assert cfg.docs_dir.is_dir()
