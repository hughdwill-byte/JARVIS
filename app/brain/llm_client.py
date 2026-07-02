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
import shutil
import subprocess

from app.config import Config
from app.logger import get_logger
from app.prompts import AGENT_SYSTEM_PROMPT, SYSTEM_PROMPT

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
    """Shared routing heuristics for every backend."""
    if force_smart:
        return cfg.llm_model_smart
    lowered = user_text.lower()
    if len(user_text) > _HARD_LENGTH or any(h in lowered for h in _HARD_HINTS):
        return cfg.llm_model_smart
    return cfg.llm_model_fast


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
        base = f"Claude API ({self.cfg.llm_model_fast} / {self.cfg.llm_model_smart})"
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

        system = SYSTEM_PROMPT
        if context_block:
            system += "\n\n--- CURRENT CONTEXT ---\n" + context_block

        messages = list(history or [])
        messages.append({"role": "user", "content": user_text})

        model = self.pick_model(user_text, force_smart)
        search = web_search_tool(self.cfg)
        try:
            resp = self._client.messages.create(
                model=model,
                max_tokens=max_tokens or self.cfg.llm_max_tokens,
                system=system,
                messages=messages,
                **({"tools": [search]} if search else {}),
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
        system = SYSTEM_PROMPT
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
        return self._run(task, system, self.cfg.llm_model_smart, allowed_tools=allowed,
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
        if force_smart and self.cc.available:  # big task -> free on the subscription
            return self.cc.chat(user_text, history, context_block, True, max_tokens)
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
    return LLMClient(cfg)  # "anthropic", or "none" -> offline fallbacks
