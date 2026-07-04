"""Local models via Ollama, and the local-first router.

  OllamaClient      — chat on a model running on THIS machine (free, private,
                      works offline). Talks to Ollama's REST API with the
                      standard library only — no new dependencies.
  LocalFirstClient  — the cheapest sensible setup: everyday chat goes to the
                      local model; hard questions, deep work, vision and agent
                      tasks go to the cloud (Claude API). Either side being
                      missing degrades gracefully to the other.

Pick with LLM_PROVIDER = ollama | local_first. Recommended local models
(good tool/instruction behaviour on ~8GB): qwen3:8b (default), llama3.2,
gemma3. Install: https://ollama.com then `ollama pull qwen3:8b`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from app.brain import usage
from app.brain.llm_client import LLMClient, _pick_model
from app.config import Config
from app.logger import get_logger
from app.prompts import SYSTEM_PROMPT, current_datetime_line

log = get_logger("ollama")

_PING_TTL_S = 30  # re-check a down server at most this often

OLLAMA_MISSING = (
    "The local model isn't reachable. Install Ollama from https://ollama.com, "
    "run `ollama pull {model}`, and make sure it's running (it starts "
    "automatically on login). Host checked: {host}"
)


class OllamaClient:
    """Chat against a local Ollama server. Free, private, offline-capable."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._ping_ok: bool | None = None
        self._ping_at: float = 0.0

    # --- availability ---------------------------------------------------
    @property
    def available(self) -> bool:
        """True if the Ollama server answers. Cached; retries a down server
        every 30s so JARVIS recovers when Ollama is started later."""
        now = time.monotonic()
        if self._ping_ok is True:
            return True
        if self._ping_ok is False and now - self._ping_at < _PING_TTL_S:
            return False
        self._ping_ok = self._ping()
        self._ping_at = now
        return self._ping_ok

    def _ping(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.cfg.ollama_host}/api/tags",
                                        timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    @property
    def raw(self):
        return None  # no Anthropic SDK client; agent mode needs the cloud

    def describe(self) -> str:
        state = "OK" if self.available else "not reachable — is Ollama running?"
        return f"Ollama local ({self.cfg.ollama_model} at {self.cfg.ollama_host}; {state})"

    def pick_model(self, user_text: str, force_smart: bool = False) -> str:
        return self.cfg.ollama_model  # one local model for everything

    # --- chat -------------------------------------------------------------
    def chat(self, user_text: str, history: list[dict] | None = None,
             context_block: str = "", force_smart: bool = False,
             max_tokens: int | None = None) -> str:
        if not self.available:
            return OLLAMA_MISSING.format(model=self.cfg.ollama_model,
                                         host=self.cfg.ollama_host)
        system = SYSTEM_PROMPT + "\n\n" + current_datetime_line()
        if context_block:
            system += "\n\n--- CURRENT CONTEXT ---\n" + context_block
        messages = [{"role": "system", "content": system}]
        messages += list(history or [])
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": self.cfg.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens or self.cfg.llm_max_tokens},
        }
        started = time.monotonic()
        try:
            req = urllib.request.Request(
                f"{self.cfg.ollama_host}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.cfg.ollama_timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")[:200]
            except Exception:
                pass
            if exc.code == 404 or "not found" in body.lower():
                return (f"Ollama is running but the model '{self.cfg.ollama_model}' "
                        f"isn't installed. Run: ollama pull {self.cfg.ollama_model}")
            log.error("Ollama HTTP %s: %s", exc.code, body)
            return f"The local model request failed (HTTP {exc.code}). {body}"
        except Exception as exc:
            self._ping_ok = None  # force a re-ping next time
            log.error("Ollama call failed: %s", exc)
            return ("The local model didn't answer "
                    f"({exc.__class__.__name__}). Is Ollama still running?")

        usage.record("ollama", self.cfg.ollama_model,
                     data.get("prompt_eval_count", 0), data.get("eval_count", 0),
                     int((time.monotonic() - started) * 1000))
        reply = (data.get("message") or {}).get("content", "")
        return _strip_think(reply).strip() or "(no reply from the local model)"

    def analyze_image(self, image_b64: str, media_type: str, prompt: str) -> str:
        return ("Vision needs the cloud brain — snapshots aren't analysed on the "
                "local model. Add an API key in Settings -> AI Brain (provider "
                "'local_first' keeps chat local and uses the cloud only for this).")


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks that reasoning models (qwen3, deepseek)
    emit — the user should hear the answer, not the deliberation."""
    while "<think>" in text:
        start = text.find("<think>")
        end = text.find("</think>", start)
        if end == -1:
            text = text[:start]
            break
        text = text[:start] + text[end + len("</think>"):]
    return text


class LocalFirstClient:
    """Everyday chat on the free local model; cloud only when it's worth it.

    Routing (per message):
      easy chat                -> Ollama ($0, private)
      hard / long / forced    -> cloud smart model
      deep ("use opus")       -> cloud deep model
      vision, documents        -> cloud (force_smart callers)
      agent tasks              -> cloud (the tool loop needs the Claude API)
    Either side missing? The other handles everything it can.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.ollama = OllamaClient(cfg)
        self.api = LLMClient(cfg)

    @property
    def available(self) -> bool:
        return self.ollama.available or self.api.available

    @property
    def raw(self):
        # None on purpose: free chat must NOT ride the cloud tool loop.
        # Action-shaped requests reach the cloud agent via assistant routing.
        return None

    def describe(self) -> str:
        local = "OK" if self.ollama.available else "down"
        cloud = "OK" if self.api.available else "no key"
        return (f"Local-first — {self.cfg.ollama_model} for everyday chat "
                f"(local {local}), cloud for heavy work (API {cloud})")

    def pick_model(self, user_text: str, force_smart: bool = False) -> str:
        cloud_model = _pick_model(self.cfg, user_text, force_smart)
        if self._wants_cloud(user_text, force_smart):
            return cloud_model
        return self.cfg.ollama_model

    def _wants_cloud(self, user_text: str, force_smart: bool) -> bool:
        """Cloud when the request earned the smart/deep tier AND a key exists."""
        if not self.api.available:
            return False
        if not self.ollama.available:
            return True
        cloud_model = _pick_model(self.cfg, user_text, force_smart)
        return cloud_model != self.cfg.llm_model_fast

    def chat(self, user_text: str, history: list[dict] | None = None,
             context_block: str = "", force_smart: bool = False,
             max_tokens: int | None = None) -> str:
        if self._wants_cloud(user_text, force_smart):
            return self.api.chat(user_text, history=history, context_block=context_block,
                                 force_smart=force_smart, max_tokens=max_tokens)
        if self.ollama.available:
            return self.ollama.chat(user_text, history=history,
                                    context_block=context_block,
                                    force_smart=force_smart, max_tokens=max_tokens)
        # no local server: the API path answers (or explains the missing key)
        return self.api.chat(user_text, history=history, context_block=context_block,
                             force_smart=force_smart, max_tokens=max_tokens)

    def analyze_image(self, image_b64: str, media_type: str, prompt: str) -> str:
        if self.api.available:
            return self.api.analyze_image(image_b64, media_type, prompt)
        return self.ollama.analyze_image(image_b64, media_type, prompt)

    _explain_error = LLMClient._explain_error
