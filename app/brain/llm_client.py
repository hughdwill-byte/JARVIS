"""LLM brains: three interchangeable backends behind one interface.

  LLMClient        — the Anthropic API (needs a key; fastest; default)
  ClaudeCodeClient — the Claude Code CLI, billed to a Claude Pro/Max
                     subscription (no API cost; a few seconds slower per turn)
  HybridClient     — chat on the API for snappy replies; big tasks
                     (vision, documents) on the subscription for the lower bill

Pick with LLM_PROVIDER = anthropic | claude_code | hybrid | none
(Settings -> AI Brain -> "Brain source"). create_llm_client() is the factory.

Cost strategy baked in:
- Everyday chat goes to the FAST (cheap) model.
- Vision, long documents, and requests flagged "hard" go to the SMART model.
- Context is trimmed to a fixed number of turns before every call.
- Images are resized before upload (see vision/image_analyzer.py).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from typing import Callable

from app.brain import usage
from app.config import Config
from app.logger import get_logger
from app.prompts import AGENT_SYSTEM_PROMPT, SYSTEM_PROMPT, current_datetime_line

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

# Phrases that summon the DEEP (premium, e.g. Opus) model. Kept narrow on
# purpose: it's the priciest tier, so it only runs when clearly asked for —
# either by naming the kind of output ("in-depth report", "deep dive") or by
# asking outright ("use opus"). Ordinary chat never lands here.
_DEEP_HINTS = (
    "in-depth", "in depth", "deep dive", "comprehensive",
    "thorough analysis", "thorough report", "detailed report", "full report",
    "use opus", "your best model", "the big model",
)

# Questions that need up-to-the-minute facts a local model can't have (no web,
# fixed knowledge cutoff). In local_first these are routed to the CLOUD, which
# can web-search and actually answer them.
_FRESH_HINTS = (
    "last night", "yesterday", "today", "tonight", "this morning",
    "this afternoon", "this evening", "this week", "this weekend",
    "right now", "currently", "at the moment", "latest", "recent",
    "just happened", "breaking", "as of", "so far this",
    "who won", "who is winning", "who's winning", "final score", "the score",
    "scores", "fixture", "results", "standings", "leaderboard",
    "news", "headline", "weather", "forecast",
    "price of", "stock price", "share price", "exchange rate",
    "how much is", "what time", "is it open", "opening hours",
    "world cup", "premier league", "election", "who is the current",
    "who's the current", "release date", "came out",
)

# Signs the model punted because it lacks current info / web access. Triggers a
# cloud retry so the user still gets a real answer.
_PUNT_PHRASES = (
    "real-time", "real time information", "realtime",
    "knowledge cutoff", "knowledge cut-off", "knowledge cut off",
    "as of my last", "as of my knowledge", "as of my training", "my last update",
    "don't have access to", "do not have access to", "no access to",
    "can't browse", "cannot browse", "can't access the internet",
    "unable to access", "not able to access", "can't provide real",
    "cannot provide real", "don't have current", "don't have real-time",
    "don't have the latest", "up-to-date information", "up to date information",
    "beyond my training", "after my training", "browse the internet",
    "i cannot look", "i can't look up", "check a live", "check the latest",
)


def needs_current_info(text: str) -> bool:
    """True if the question likely needs current facts the local model can't have."""
    low = text.lower()
    return any(h in low for h in _FRESH_HINTS)


def looks_unanswered(reply: str) -> bool:
    """True if a reply reads like the model gave up for lack of current info."""
    low = (reply or "").lower()
    return any(p in low for p in _PUNT_PHRASES)
# Deep work usually means long output; 1024 tokens would truncate a report.
DEEP_MAX_TOKENS = 8192


_SENTENCE_END = re.compile(r"(?<=[.!?])[\s\n]+")


class SentenceStreamer:
    """Feeds streamed text deltas out as complete sentences (for live TTS)."""

    def __init__(self, emit: Callable[[str], None]):
        self.emit = emit
        self._buf = ""

    def feed(self, delta: str) -> None:
        self._buf += delta
        parts = _SENTENCE_END.split(self._buf)
        if len(parts) > 1:
            for sentence in parts[:-1]:
                if sentence.strip():
                    self.emit(sentence.strip())
            self._buf = parts[-1]

    def flush(self) -> None:
        if self._buf.strip():
            self.emit(self._buf.strip())
        self._buf = ""


def cached_system(static: str, dynamic: str = "") -> list[dict]:
    """System prompt as blocks with prompt caching on the static part.

    The static prefix (persona + rules, identical on every call) gets a
    cache_control breakpoint: the API stores it for ~5 minutes and re-reads
    cost 10% of normal input price — a big win for back-and-forth voice chat.
    Dynamic content (date, tasks, desk context) stays in an uncached block so
    it never breaks the cache. See:
    https://platform.claude.com/docs/en/build-with-claude/prompt-caching
    """
    blocks: list[dict] = [{
        "type": "text",
        "text": static,
        "cache_control": {"type": "ephemeral"},
    }]
    if dynamic:
        blocks.append({"type": "text", "text": dynamic})
    return blocks


def web_search_tool(cfg: Config) -> dict | None:
    """Anthropic's server-side web search tool — lets the model look things up
    (news, scores, docs) with no client-side execution. ~$0.01 per search."""
    if not cfg.web_search_enabled:
        return None
    return {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": cfg.web_search_max_uses,
    }


def _pick_model(cfg: Config, user_text: str, force_smart: bool = False) -> str:
    """Shared routing heuristics for every backend.

    Three tiers, cheapest wins unless the request earns an upgrade:
      fast (default) -> smart (hard/long/forced) -> deep (explicitly summoned).
    Deep is checked first so "/agent write an in-depth report" upgrades past
    the forced-smart tier.
    """
    lowered = user_text.lower()
    if any(h in lowered for h in _DEEP_HINTS):
        return cfg.llm_model_deep
    if force_smart:
        return cfg.llm_model_smart
    if len(user_text) > _HARD_LENGTH or any(h in lowered for h in _HARD_HINTS):
        return cfg.llm_model_smart
    return cfg.llm_model_fast


def max_tokens_for(cfg: Config, model: str, requested: int | None = None) -> int:
    """Reply-length cap for a model: deep work gets room to write a real report."""
    base = requested or cfg.llm_max_tokens
    if model == cfg.llm_model_deep:
        return max(base, DEEP_MAX_TOKENS)
    return base


def record_api_usage(model: str, resp, started: float) -> None:
    """Log tokens/cost for one Anthropic API response (no-op if untracked)."""
    u = getattr(resp, "usage", None)
    if u is not None:
        usage.record("api", model,
                     getattr(u, "input_tokens", 0) or 0,
                     getattr(u, "output_tokens", 0) or 0,
                     int((time.monotonic() - started) * 1000))


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

    def describe(self) -> str:
        base = (f"Claude API ({self.cfg.llm_model_fast} / {self.cfg.llm_model_smart}; "
                f"{self.cfg.llm_model_deep} on demand)")
        return base if self.available else base + " — set the API key in Settings"

    def pick_model(self, user_text: str, force_smart: bool = False) -> str:
        return _pick_model(self.cfg, user_text, force_smart)

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

        dynamic = current_datetime_line()
        if context_block:
            dynamic += "\n\n--- CURRENT CONTEXT ---\n" + context_block
        system = cached_system(SYSTEM_PROMPT, dynamic)

        messages = list(history or [])
        messages.append({"role": "user", "content": user_text})

        model = self.pick_model(user_text, force_smart)
        search = web_search_tool(self.cfg)
        started = time.monotonic()
        try:
            resp = self._client.messages.create(
                model=model,
                max_tokens=max_tokens_for(self.cfg, model, max_tokens),
                system=system,
                messages=messages,
                **({"tools": [search]} if search else {}),
            )
            record_api_usage(model, resp, started)
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        except Exception as exc:
            log.error("LLM call failed (%s): %s", model, exc)
            return self._explain_error(exc)

    def analyze_image(self, image_b64: str, media_type: str, prompt: str) -> str:
        """Send one image + instruction to the smart model."""
        if not self.available:
            return OFFLINE_NOTICE
        started = time.monotonic()
        try:
            resp = self._client.messages.create(
                model=self.cfg.llm_model_smart,
                max_tokens=self.cfg.llm_max_tokens,
                system=cached_system(SYSTEM_PROMPT),
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
            record_api_usage(self.cfg.llm_model_smart, resp, started)
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


CLAUDE_CODE_MISSING = (
    "The Claude Code backend isn't ready. One-time setup in a terminal: "
    "1) install Node.js (macOS: brew install node), "
    "2) npm install -g @anthropic-ai/claude-code, "
    "3) run `claude` once and log in with your Claude Pro account, "
    "4) restart JARVIS. (Or switch Brain source back to 'anthropic' in Settings.)"
)

# Where the claude binary hides when it's not on PATH — common when JARVIS is
# launched from Finder/a shortcut, which doesn't inherit your shell's PATH.
_CLAUDE_CLI_FALLBACKS = (
    "~/.claude/local/claude",       # native installer
    "~/.local/bin/claude",          # native installer (newer)
    "/opt/homebrew/bin/claude",     # npm -g on Apple Silicon Macs
    "/usr/local/bin/claude",        # npm -g on Intel Macs / Linux
    "~/.npm-global/bin/claude",     # custom npm prefix
    "~/AppData/Roaming/npm/claude.cmd",  # npm -g on Windows
)


def _find_claude_cli() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    for candidate in _CLAUDE_CLI_FALLBACKS:
        path = os.path.expanduser(candidate)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None

_CC_CHAT_TIMEOUT_S = 180
_CC_TASK_TIMEOUT_S = 600


class ClaudeCodeClient:
    """Brain backed by the Claude Code CLI — billed to a Claude Pro/Max subscription.

    Runs `claude -p` headless per request. The ANTHROPIC_API_KEY is removed from
    the subprocess environment on purpose: with a key present Claude Code would
    bill the API instead of the subscription, defeating the point.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._cli = _find_claude_cli()

    @property
    def available(self) -> bool:
        return self._cli is not None

    @property
    def raw(self):
        return None  # no Anthropic SDK client; agent tool-loop uses agent_task instead

    def describe(self) -> str:
        if not self.available:
            return "Claude Code (Pro subscription) — CLI not found; " + CLAUDE_CODE_MISSING
        return "Claude Code (billed to your Claude Pro subscription; slower per reply)"

    def pick_model(self, user_text: str, force_smart: bool = False) -> str:
        return _pick_model(self.cfg, user_text, force_smart)

    def _run(self, prompt: str, system: str, model: str,
             allowed_tools: list[str] | None = None,
             permission_mode: str | None = None,
             cwd: str | None = None,
             timeout: int = _CC_CHAT_TIMEOUT_S) -> str:
        if not self.available:
            return CLAUDE_CODE_MISSING
        cmd = [self._cli, "-p", prompt, "--output-format", "json", "--model", model]
        if system:
            cmd += ["--system-prompt", system]
        if allowed_tools:
            cmd += ["--allowedTools", ",".join(allowed_tools)]
        if permission_mode:
            cmd += ["--permission-mode", permission_mode]
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout, cwd=cwd, env=env)
        except subprocess.TimeoutExpired:
            return f"Claude Code didn't answer within {timeout}s — try again or switch Brain source to 'anthropic'."
        except OSError as exc:
            return f"Couldn't start Claude Code: {exc}"
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:400]
            if "login" in err.lower() or "authent" in err.lower() or "api key" in err.lower():
                return ("Claude Code isn't logged in. Open a terminal, run `claude`, "
                        "and sign in with your Claude Pro account — then try again.")
            return f"Claude Code failed: {err or 'unknown error'}"
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return proc.stdout.strip() or "(Claude Code returned no output)"
        if data.get("is_error"):
            return f"Claude Code reported an error: {data.get('result', 'unknown')}"
        return str(data.get("result", "")).strip() or "(no reply)"

    def chat(self, user_text: str, history: list[dict] | None = None,
             context_block: str = "", force_smart: bool = False,
             max_tokens: int | None = None) -> str:
        system = SYSTEM_PROMPT + "\n\n" + current_datetime_line()
        if context_block:
            system += "\n\n--- CURRENT CONTEXT ---\n" + context_block
        if history:
            lines = [f"{'User' if m['role'] == 'user' else 'JARVIS'}: {m['content']}"
                     for m in history]
            prompt = ("Continue this conversation as JARVIS; reply with your next "
                      "message only.\n\n" + "\n\n".join(lines) + f"\n\nUser: {user_text}")
        else:
            prompt = user_text
        search_tools = ["WebSearch", "WebFetch"] if self.cfg.web_search_enabled else None
        return self._run(prompt, system, self.pick_model(user_text, force_smart),
                         allowed_tools=search_tools)

    def analyze_image_file(self, image_path: str, prompt: str) -> str:
        """Vision via Claude Code's Read tool (it can view image files)."""
        task = (f"Use the Read tool to view the image file at {image_path}, "
                f"then answer this about it:\n{prompt}")
        return self._run(task, SYSTEM_PROMPT, self.cfg.llm_model_smart,
                         allowed_tools=["Read"])

    def analyze_image(self, image_b64: str, media_type: str, prompt: str) -> str:
        # The CLI takes file paths, not base64 — callers should prefer
        # analyze_image_file (ImageAnalyzer does this automatically).
        return ("This brain backend reads images from files; the snapshot analysis "
                "path should have used the file directly — please report this.")

    def agent_task(self, task: str, workdir: str, auto_approve: bool) -> str:
        """/agent via Claude Code's own tools. Read-only unless auto-approve is on
        (headless runs can't show per-action y/N prompts)."""
        if auto_approve:
            allowed = ["Read", "Glob", "Grep", "Bash", "Edit", "Write",
                       "WebSearch", "WebFetch"]
            mode = "acceptEdits"
            system = AGENT_SYSTEM_PROMPT
        else:
            allowed = ["Read", "Glob", "Grep", "WebSearch", "WebFetch"]
            mode = None
            system = (AGENT_SYSTEM_PROMPT +
                      "\n\nNOTE: you currently have READ-ONLY access. If the task needs "
                      "changes, report exactly what you would do and tell the user to "
                      "enable 'Act without asking' in Settings -> Computer & Apps "
                      "(or switch Brain source to 'anthropic'/'hybrid' for per-action "
                      "approval prompts).")
        # force_smart floor, but a deep-hinted task ("in-depth report") gets the
        # deep model — free here anyway, it's billed to the subscription.
        model = self.pick_model(task, force_smart=True)
        return self._run(task, system, model, allowed_tools=allowed,
                         permission_mode=mode, cwd=workdir, timeout=_CC_TASK_TIMEOUT_S)

    _explain_error = LLMClient._explain_error


class HybridClient:
    """Snappy chat on the API; big tasks (vision, documents) on the subscription."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.api = LLMClient(cfg)
        self.cc = ClaudeCodeClient(cfg)

    @property
    def available(self) -> bool:
        return self.api.available or self.cc.available

    @property
    def raw(self):
        return self.api.raw  # agent tool-loop (interactive approvals) rides the API

    def describe(self) -> str:
        parts = []
        parts.append("API " + ("OK" if self.api.available else "missing key"))
        parts.append("Claude Code " + ("OK" if self.cc.available else "not set up"))
        return f"Hybrid — chat on the API, big tasks on your Pro plan ({'; '.join(parts)})"

    def pick_model(self, user_text: str, force_smart: bool = False) -> str:
        return _pick_model(self.cfg, user_text, force_smart)

    def chat(self, user_text: str, history: list[dict] | None = None,
             context_block: str = "", force_smart: bool = False,
             max_tokens: int | None = None) -> str:
        # Big tasks -> free on the subscription. That includes deep-hinted
        # requests ("in-depth report"): Opus on the Pro plan costs $0 extra.
        wants_deep = self.pick_model(user_text, force_smart) == self.cfg.llm_model_deep
        if (force_smart or wants_deep) and self.cc.available:
            return self.cc.chat(user_text, history, context_block, force_smart, max_tokens)
        target = self.api if self.api.available else self.cc
        return target.chat(user_text, history=history, context_block=context_block,
                           force_smart=force_smart, max_tokens=max_tokens)

    def analyze_image_file(self, image_path: str, prompt: str) -> str:
        if self.cc.available:
            return self.cc.analyze_image_file(image_path, prompt)
        # runtime import avoids a module-load cycle (image_analyzer imports us)
        from app.vision.image_analyzer import encode_image
        b64, media = encode_image(image_path, self.cfg.vision_max_image_edge)
        return self.api.analyze_image(b64, media, prompt)

    def analyze_image(self, image_b64: str, media_type: str, prompt: str) -> str:
        return self.api.analyze_image(image_b64, media_type, prompt)

    def agent_task(self, task: str, workdir: str, auto_approve: bool) -> str:
        return self.cc.agent_task(task, workdir, auto_approve)

    _explain_error = LLMClient._explain_error


def create_llm_client(cfg: Config):
    """Factory: the right brain for LLM_PROVIDER."""
    if cfg.llm_provider == "claude_code":
        return ClaudeCodeClient(cfg)
    if cfg.llm_provider == "hybrid":
        return HybridClient(cfg)
    if cfg.llm_provider in ("ollama", "local_first"):
        # runtime import: ollama_client imports from this module
        from app.brain.ollama_client import LocalFirstClient, OllamaClient
        return OllamaClient(cfg) if cfg.llm_provider == "ollama" else LocalFirstClient(cfg)
    return LLMClient(cfg)  # "anthropic", or "none" -> offline fallbacks
