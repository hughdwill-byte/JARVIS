"""LLM client: Claude API with cheap/smart model routing and offline fallback.

Cost strategy baked in:
- Everyday chat goes to the FAST (cheap) model.
- Vision, long documents, and requests flagged "hard" go to the SMART model.
- Context is trimmed to a fixed number of turns before every call.
- Images are resized before upload (see vision/image_analyzer.py).
"""

from __future__ import annotations

from app.config import Config
from app.logger import get_logger
from app.prompts import SYSTEM_PROMPT

log = get_logger("llm")

OFFLINE_NOTICE = (
    "I'm running without an LLM API key, so I can't generate a smart reply. "
    "Local features (notes, tasks, snapshots, memory) still work. "
    "To enable my brain: put ANTHROPIC_API_KEY=<your key> in the .env file and restart me."
)

# Rough heuristics for when a request deserves the stronger model.
_HARD_HINTS = (
    "prove", "derive", "step by step", "debug", "refactor", "architecture",
    "essay feedback", "review my draft", "explain in depth", "research plan",
)
_HARD_LENGTH = 600  # chars — long pasted content usually means a real task


class LLMClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._client = None
        if cfg.llm_available:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
            except ImportError:
                log.error("anthropic package not installed; run: pip install anthropic")
            except Exception as exc:
                log.error("Could not init Anthropic client: %s", exc)

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def raw(self):
        """The underlying Anthropic client (used by agent mode's tool loop)."""
        return self._client

    def pick_model(self, user_text: str, force_smart: bool = False) -> str:
        if force_smart:
            return self.cfg.llm_model_smart
        lowered = user_text.lower()
        if len(user_text) > _HARD_LENGTH or any(h in lowered for h in _HARD_HINTS):
            return self.cfg.llm_model_smart
        return self.cfg.llm_model_fast

    def chat(
        self,
        user_text: str,
        history: list[dict] | None = None,
        context_block: str = "",
        force_smart: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        """One chat turn. `history` is [{'role': 'user'|'assistant', 'content': str}, ...]."""
        if not self.available:
            return OFFLINE_NOTICE

        system = SYSTEM_PROMPT
        if context_block:
            system += "\n\n--- CURRENT CONTEXT ---\n" + context_block

        messages = list(history or [])
        messages.append({"role": "user", "content": user_text})

        model = self.pick_model(user_text, force_smart)
        try:
            resp = self._client.messages.create(
                model=model,
                max_tokens=max_tokens or self.cfg.llm_max_tokens,
                system=system,
                messages=messages,
            )
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        except Exception as exc:
            log.error("LLM call failed (%s): %s", model, exc)
            return self._explain_error(exc)

    def analyze_image(self, image_b64: str, media_type: str, prompt: str) -> str:
        """Send one image + instruction to the smart model."""
        if not self.available:
            return OFFLINE_NOTICE
        try:
            resp = self._client.messages.create(
                model=self.cfg.llm_model_smart,
                max_tokens=self.cfg.llm_max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image",
                         "source": {"type": "base64", "media_type": media_type,
                                    "data": image_b64}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        except Exception as exc:
            log.error("Vision call failed: %s", exc)
            return self._explain_error(exc)

    @staticmethod
    def _explain_error(exc: Exception) -> str:
        text = str(exc)
        if "authentication" in text.lower() or "401" in text:
            return ("My API key was rejected. Check ANTHROPIC_API_KEY in your .env "
                    "file — no quotes, no spaces — then restart me.")
        if "rate" in text.lower() or "429" in text:
            return "The API is rate-limiting us. Wait a minute and try again."
        if "overloaded" in text.lower() or "529" in text:
            return "The API is overloaded right now. Try again shortly."
        return f"The LLM request failed: {text}. Check your internet connection and API key."
