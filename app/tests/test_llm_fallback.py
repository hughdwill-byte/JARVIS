"""LLM fallback: no key -> graceful offline behaviour, never a crash."""

from app.assistant import Assistant
from app.brain.llm_client import OFFLINE_NOTICE, LLMClient


def test_offline_chat_returns_notice(cfg):
    llm = LLMClient(cfg)
    assert not llm.available
    assert llm.chat("hello") == OFFLINE_NOTICE
    assert llm.analyze_image("abc", "image/jpeg", "describe") == OFFLINE_NOTICE


def test_model_routing(cfg):
    llm = LLMClient(cfg)
    assert llm.pick_model("hi") == cfg.llm_model_fast
    assert llm.pick_model("debug this crash for me") == cfg.llm_model_smart
    assert llm.pick_model("x" * 700) == cfg.llm_model_smart
    assert llm.pick_model("hi", force_smart=True) == cfg.llm_model_smart


def test_assistant_runs_fully_offline(cfg):
    """Whole assistant works with zero API keys and zero devices."""
    bot = Assistant(cfg)
    try:
        assert "Noted" in bot.handle("/note offline test").text
        assert "added" in bot.handle("/task offline task").text
        assert "offline task" in bot.handle("/tasks").text
        chat = bot.handle("what's the capital of France?")
        assert "API key" in chat.text  # offline notice, not a traceback
        assert "/help" in bot.handle("/nonexistent").text
    finally:
        bot.close()


def test_integrity_check_blocks_before_api(cfg):
    bot = Assistant(cfg)
    try:
        reply = bot.handle("write my essay so I can submit it tomorrow")
        assert "won't" in reply.text.lower()
    finally:
        bot.close()
