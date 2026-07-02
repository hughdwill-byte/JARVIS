"""Agent mode: JARVIS uses your computer and connected apps to complete tasks.

Cowork-style multi-step loop: the model plans, calls tools, sees results,
and keeps going until the task is done (or the step limit hits).

Local tools: list folders, read files, write files, run shell commands,
open apps/URLs. Plus every tool from connected MCP apps (Gmail, calendar…).

Safety model:
- File access is restricted to AGENT_ALLOWED_DIRS (default: your home folder).
- "Dangerous" actions (writing files, running commands, anything on an app
  that sends/creates/deletes) require your approval — a y/N prompt in the
  terminal, or the auto-approve setting if you've opted in.
- Content fetched from apps (emails!) is untrusted: the agent's instructions
  tell it to treat embedded "instructions" in emails/pages as data, never
  as commands, and every action it takes is shown to you.
"""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from app.brain.llm_client import LLMClient, web_search_tool
from app.config import Config
from app.logger import get_logger
from app.prompts import AGENT_SYSTEM_PROMPT, CHAT_TOOLS_ADDENDUM, SYSTEM_PROMPT

if TYPE_CHECKING:
    from app.brain.mcp_client import MCPManager

log = get_logger("agent")

READ_CAP = 50_000        # chars of a file shown to the model
OUTPUT_CAP = 8_000       # chars of command output / tool result
COMMAND_TIMEOUT_S = 90

LOCAL_TOOL_SCHEMAS = [
    {"name": "list_dir",
     "description": "List the files and folders inside a directory on this computer.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Directory path, e.g. ~/Downloads"}},
         "required": ["path"]}},
    {"name": "read_file",
     "description": "Read a text file on this computer (code, notes, csv, config...).",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file",
     "description": "Create or overwrite a text file. Requires user approval.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"},
         "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "run_command",
     "description": "Run a shell command on this computer and return its output. "
                    "Requires user approval.",
     "input_schema": {"type": "object", "properties": {
         "command": {"type": "string"}}, "required": ["command"]}},
    {"name": "open_app",
     "description": "Open a file, folder, application, or URL in the user's desktop "
                    "environment (their default browser/app). Requires user approval.",
     "input_schema": {"type": "object", "properties": {
         "target": {"type": "string",
                    "description": "A path or a URL, e.g. ~/report.pdf or https://..."}},
         "required": ["target"]}},
]

# Local tools that always need a yes from the user.
DANGEROUS_LOCAL = {"write_file", "run_command", "open_app"}
# MCP tools are gated when their name implies a state change.
_WRITEY_HINTS = ("send", "create", "delete", "update", "write", "move", "archive",
                 "reply", "draft", "modify", "remove", "post", "trash", "label")


def needs_approval(tool_name: str) -> bool:
    if tool_name in DANGEROUS_LOCAL:
        return True
    if "__" in tool_name:  # an MCP app tool
        return any(h in tool_name.split("__", 1)[1].lower() for h in _WRITEY_HINTS)
    return False


class ToolError(Exception):
    """Raised by tool executors; message goes back to the model as an error result."""


class AgentTools:
    """Local tool executors, sandboxed to the allowed directories."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.allowed_dirs = [
            Path(p.strip()).expanduser().resolve()
            for p in cfg.agent_allowed_dirs.split(",") if p.strip()
        ] or [Path.home().resolve()]

    def _check_path(self, raw: str) -> Path:
        path = Path(raw).expanduser()
        resolved = (path if path.is_absolute() else self.allowed_dirs[0] / path).resolve()
        if not any(resolved == d or resolved.is_relative_to(d) for d in self.allowed_dirs):
            allowed = ", ".join(str(d) for d in self.allowed_dirs)
            raise ToolError(
                f"'{resolved}' is outside the folders I'm allowed to touch ({allowed}). "
                "The user can widen this in Settings -> Computer & Apps."
            )
        return resolved

    def list_dir(self, path: str) -> str:
        target = self._check_path(path)
        if not target.is_dir():
            raise ToolError(f"Not a directory: {target}")
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = [f"{'[dir] ' if e.is_dir() else '     '}{e.name}" for e in entries[:200]]
        if len(entries) > 200:
            lines.append(f"... and {len(entries) - 200} more")
        return f"{target}:\n" + ("\n".join(lines) if lines else "(empty)")

    def read_file(self, path: str) -> str:
        target = self._check_path(path)
        if not target.is_file():
            raise ToolError(f"Not a file: {target}")
        if target.stat().st_size > 5_000_000:
            raise ToolError(f"{target.name} is too large to read ({target.stat().st_size:,} bytes).")
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ToolError(f"Could not read {target}: {exc}")
        if len(text) > READ_CAP:
            return text[:READ_CAP] + f"\n...[truncated — file is {len(text):,} chars]"
        return text or "(empty file)"

    def write_file(self, path: str, content: str) -> str:
        target = self._check_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content):,} chars to {target}"

    def run_command(self, command: str) -> str:
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=COMMAND_TIMEOUT_S, cwd=self.allowed_dirs[0],
            )
        except subprocess.TimeoutExpired:
            raise ToolError(f"Command timed out after {COMMAND_TIMEOUT_S}s.")
        out = (proc.stdout or "") + (("\n[stderr] " + proc.stderr) if proc.stderr else "")
        out = out.strip()[:OUTPUT_CAP]
        return f"[exit {proc.returncode}]\n{out or '(no output)'}"

    def open_app(self, target: str) -> str:
        if target.startswith(("http://", "https://")):
            webbrowser.open(target)
            return f"Opened {target} in the browser."
        path = self._check_path(target)
        if not path.exists():
            raise ToolError(f"Nothing at {path}")
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform == "win32":
            import os
            os.startfile(str(path))  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return f"Opened {path}."

    def execute(self, name: str, args: dict) -> str:
        handler = getattr(self, name, None)
        if handler is None:
            raise ToolError(f"Unknown local tool: {name}")
        return handler(**args)


ApprovalFn = Callable[[str, str], bool]


def describe_action(name: str, args: dict) -> str:
    """One human-readable line describing a proposed tool call."""
    if name == "write_file":
        return f"write {len(args.get('content', '')):,} chars to {args.get('path')}"
    if name == "run_command":
        return f"run: {args.get('command')}"
    if name == "open_app":
        return f"open: {args.get('target')}"
    if "__" in name:
        server, tool = name.split("__", 1)
        brief = ", ".join(f"{k}={str(v)[:60]}" for k, v in list(args.items())[:4])
        return f"{server} app -> {tool}({brief})"
    return f"{name}({', '.join(f'{k}={str(v)[:60]}' for k, v in list(args.items())[:4])})"


class Agent:
    def __init__(self, cfg: Config, llm: LLMClient, tools: AgentTools,
                 approve: ApprovalFn, mcp: "MCPManager | None" = None):
        self.cfg = cfg
        self.llm = llm
        self.tools = tools
        self.approve = approve
        self.mcp = mcp

    def run(self, task: str, on_action: Callable[[str], None] = print) -> str:
        """Explicit /agent invocation: task-focused prompt, smart model, action log."""
        if not self.llm.available:
            return ("Agent mode needs the LLM — add your Anthropic API key in "
                    "Settings -> AI Brain and press Save & Apply.")
        final, actions = self._loop(
            messages=[{"role": "user", "content": task}],
            system=AGENT_SYSTEM_PROMPT,
            model=self.cfg.llm_model_smart,
            on_action=on_action,
        )
        return self._with_action_log(final, actions)

    def run_conversation(
        self,
        user_text: str,
        history: list[dict] | None = None,
        context_block: str = "",
        on_action: Callable[[str], None] = print,
    ) -> tuple[str, list[str]]:
        """Normal chat with tools available: JARVIS acts only when the request
        needs the computer/apps, otherwise it just answers. Returns (reply, actions)."""
        system = SYSTEM_PROMPT + "\n\n" + CHAT_TOOLS_ADDENDUM
        if context_block:
            system += "\n\n--- CURRENT CONTEXT ---\n" + context_block
        messages = list(history or []) + [{"role": "user", "content": user_text}]
        # Cheap model for the first look; escalates to the smart model once it acts.
        return self._loop(messages, system, self.llm.pick_model(user_text), on_action)

    def _loop(self, messages: list[dict], system: str, model: str,
              on_action: Callable[[str], None]) -> tuple[str, list[str]]:
        schemas = list(LOCAL_TOOL_SCHEMAS)
        search = web_search_tool(self.cfg)
        if search is not None:
            schemas.append(search)  # server-side: the API runs searches itself
        if self.mcp is not None:
            schemas += self.mcp.tool_schemas()
        client = self.llm.raw
        actions: list[str] = []

        for _step in range(self.cfg.agent_max_steps):
            try:
                resp = client.messages.create(
                    model=model,
                    max_tokens=2048,
                    system=system,
                    tools=schemas,
                    messages=messages,
                )
            except Exception as exc:
                log.error("Agent LLM call failed: %s", exc)
                return self.llm._explain_error(exc), actions

            if resp.stop_reason == "pause_turn":
                # A long-running server tool (web search) paused mid-turn:
                # hand the partial content back and let it continue.
                messages.append({"role": "assistant", "content": resp.content})
                continue

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not tool_uses:
                final = "".join(b.text for b in resp.content if b.type == "text").strip()
                return final, actions

            model = self.cfg.llm_model_smart  # multi-step work deserves the smart model
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in tool_uses:
                results.append(self._execute_one(block, actions, on_action))
            messages.append({"role": "user", "content": results})

        return ("I hit the step limit before finishing — here's where I got to. "
                "You can raise the limit in Settings -> Computer & Apps."), actions

    def _execute_one(self, block, actions: list[str], on_action) -> dict:
        name, args = block.name, dict(block.input or {})
        desc = describe_action(name, args)
        result: str
        is_error = False
        if needs_approval(name) and not self.approve(name, desc):
            result = "The user declined this action. Continue without it or wrap up."
            is_error = True
            actions.append(f"(declined) {desc}")
        else:
            on_action(f"  [agent] {desc}")
            try:
                if "__" in name and self.mcp is not None:
                    result = self.mcp.call(name, args)
                else:
                    result = self.tools.execute(name, args)
                actions.append(desc)
            except ToolError as exc:
                result, is_error = str(exc), True
            except Exception as exc:
                log.exception("Agent tool %s crashed", name)
                result, is_error = f"Tool failed: {exc}", True
        return {"type": "tool_result", "tool_use_id": block.id,
                "content": result[:OUTPUT_CAP], "is_error": is_error}

    @staticmethod
    def _with_action_log(final: str, actions: list[str]) -> str:
        if not actions:
            return final or "Done — nothing needed doing."
        log_lines = "\n".join(f"  - {a}" for a in actions)
        return f"{final or 'Done.'}\n\nActions taken:\n{log_lines}"
