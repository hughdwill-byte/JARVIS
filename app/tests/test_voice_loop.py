"""Hands-free voice loop: sleep phrases, config, command wiring — no audio devices needed."""

from app.assistant import Assistant
from app.audio.voice_loop import is_noise_transcript, is_sleep_phrase, looks_like_echo
from app.config import load_config


def test_noise_transcripts_are_ignored():
    # classic Whisper hallucinations from background noise -> stay silent
    assert is_noise_transcript("Thank you.")
    assert is_noise_transcript("thanks for watching")
    assert is_noise_transcript("you")
    assert is_noise_transcript("Hmm")
    assert is_noise_transcript(".")
    # real (even terse) replies still go through
    assert not is_noise_transcript("yes")
    assert not is_noise_transcript("no thanks, close it")
    assert not is_noise_transcript("what about tomorrow?")


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


def test_sleep_phrase_requires_whole_utterance():
    """Playtest regression: 4-word TASKS must not close the microphone."""
    assert not is_sleep_phrase("shut down the server")
    assert not is_sleep_phrase("stop listening to spotify")
    assert not is_sleep_phrase("power down the pi")
    # ...while the real commands still work
    assert is_sleep_phrase("power down")
    assert is_sleep_phrase("Shut down!")


def test_echo_filter_ignores_stopwords():
    """Playtest regression: follow-ups built from common words must get through."""
    spoken = "I'll add milk and bread to your list for you now."
    assert not looks_like_echo("do that now", spoken)
    assert not looks_like_echo("for you now", spoken)
    assert not looks_like_echo("add eggs and bread too", spoken)
    # genuine echo (content words all from the spoken reply) is still caught
    assert looks_like_echo("add milk bread list", spoken)


def test_self_echo_is_disregarded():
    spoken = "Your desk has a laptop, a blue notebook, and two pens on the left."
    # mic picks up (part of) its own sentence -> discard
    assert looks_like_echo("a blue notebook and two pens", spoken)
    assert looks_like_echo("your desk has a laptop", spoken)
    # genuine user follow-ups survive, even when they share a couple of words
    assert not looks_like_echo("move the notebook to my bag list", spoken)
    assert not looks_like_echo("yes", spoken)
    assert not looks_like_echo("what pens?", spoken)
    assert not looks_like_echo("anything", "")


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
