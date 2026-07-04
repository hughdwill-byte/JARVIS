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


def test_deep_model_only_when_summoned(cfg):
    """The premium tier never fires on ordinary chat — only on explicit asks."""
    llm = LLMClient(cfg)
    assert llm.pick_model("write me an in-depth report on solar batteries") == cfg.llm_model_deep
    assert llm.pick_model("do a deep dive into my thesis topic") == cfg.llm_model_deep
    assert llm.pick_model("use opus: compare these two frameworks") == cfg.llm_model_deep
    # deep beats force_smart, so "/agent ... in-depth report" upgrades past smart
    assert llm.pick_model("an in-depth report please", force_smart=True) == cfg.llm_model_deep
    # everyday requests stay on the cheap tiers
    assert llm.pick_model("what's a good name for a cat?") == cfg.llm_model_fast
    assert llm.pick_model("summarise this paragraph for me") == cfg.llm_model_fast


def test_deep_model_gets_a_longer_reply_budget(cfg):
    from app.brain.llm_client import DEEP_MAX_TOKENS, max_tokens_for
    assert max_tokens_for(cfg, cfg.llm_model_fast) == cfg.llm_max_tokens
    assert max_tokens_for(cfg, cfg.llm_model_smart) == cfg.llm_max_tokens
    assert max_tokens_for(cfg, cfg.llm_model_deep) == DEEP_MAX_TOKENS
    # an explicit larger request is respected, never shrunk
    assert max_tokens_for(cfg, cfg.llm_model_deep, DEEP_MAX_TOKENS * 2) == DEEP_MAX_TOKENS * 2


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
