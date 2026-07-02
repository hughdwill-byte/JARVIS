"""Hands-free voice loop: sleep phrases, config, command wiring — no audio devices needed."""

from app.assistant import Assistant
from app.audio.voice_loop import is_sleep_phrase
from app.config import load_config


def test_sleep_phrases_match():
    assert is_sleep_phrase("shutdown")
    assert is_sleep_phrase("Shutdown.")
    assert is_sleep_phrase("shut down")
    assert is_sleep_phrase("stop listening")
    assert is_sleep_phrase("go to sleep")


def test_sleep_phrases_ignore_normal_speech():
    assert not is_sleep_phrase("")
    assert not is_sleep_phrase("what's on my desk")
    # 'shutdown' inside a longer sentence must NOT close the mic
    assert not is_sleep_phrase("how do I shutdown a linux server safely")


def test_wake_word_config(monkeypatch):
    monkeypatch.setenv("WAKE_WORD_ENABLED", "true")
    monkeypatch.setenv("WAKE_WORD_THRESHOLD", "0.7")
    monkeypatch.setenv("WAKE_WORD_MODEL", "hey_jarvis")
    cfg = load_config(env_file="/nonexistent/.env")
    assert cfg.wake_word_enabled is True
    assert cfg.wake_word_threshold == 0.7
    assert cfg.wake_word_model == "hey_jarvis"
    monkeypatch.delenv("WAKE_WORD_ENABLED")
    assert load_config(env_file="/nonexistent/.env").wake_word_enabled is False


def test_listen_sleep_commands_when_disabled(cfg):
    """WAKE_WORD_ENABLED=false -> commands explain how to enable, never crash."""
    bot = Assistant(cfg)
    try:
        assert "WAKE_WORD_ENABLED" in bot.handle("/listen").text
        assert "already off" in bot.handle("/sleep").text
        # Natural-phrase routing hits the same commands
        assert "already off" in bot.handle("shutdown").text
        assert "WAKE_WORD_ENABLED" in bot.handle("wake up").text
    finally:
        bot.close()


def test_voice_loop_unavailable_without_deps(cfg):
    """No sounddevice/openwakeword in CI -> clear install hint, no crash."""
    cfg.wake_word_enabled = True
    bot = Assistant(cfg)
    try:
        assert bot.voice_loop is not None
        assert not bot.voice_loop.available
        assert "pip install" in bot.voice_loop.why_unavailable()
        assert "pip install" in bot.handle("/listen").text
    finally:
        bot.close()
