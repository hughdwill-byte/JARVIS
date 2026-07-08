"""MCP client: connect JARVIS to the same app ecosystem Claude uses.

MCP (Model Context Protocol) servers provide tools for Gmail, calendars,
Notion, filesystems, and hundreds of other apps. You declare them in
`mcp_servers.json` (see `mcp_servers.example.json`), and every tool they
expose becomes available to JARVIS's agent mode automatically.

Runs each server as a child process over stdio, managed by a background
asyncio loop; the rest of JARVIS stays synchronous via the thin wrappers here.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from pathlib import Path

from app.config import Config
from app.logger import get_logger

log = get_logger("mcp")

CALL_TIMEOUT_S = 90
CONNECT_TIMEOUT_S = 45
NAME_SEP = "__"  # agent tool names look like gmail__search_emails


def mcp_deps_ok() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


def sanitize_input_schema(schema: object) -> dict:
    """Make an MCP tool's JSON schema safe to send to the Anthropic API.

    Anthropic requires each tool's ``input_schema`` to be a plain object schema
    (``"type": "object"``) and rejects ``oneOf`` / ``allOf`` / ``anyOf`` — and
    anything without a top-level object type — *at the top level* (nested ones
    inside properties are fine). Real-world connectors (Microsoft 365 / Graph,
    Canvas, …) ship tools whose top-level schema is a union, and a single one of
    those makes the ENTIRE request 400, killing every tool call in the turn.

    We coerce any such schema to a valid top-level object: keep its
    ``properties`` / ``required`` if present, otherwise fall back to an
    unconstrained object (the MCP server still validates arguments on its side).
    Schemas that are already well-formed pass through untouched.
    """
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    has_top_combinator = any(k in schema for k in ("oneOf", "allOf", "anyOf"))
    if not has_top_combinator and schema.get("type") == "object":
        return schema  # already valid — leave it alone
    cleaned: dict = {"type": "object"}
    props = schema.get("properties")
    cleaned["properties"] = props if isinstance(props, dict) else {}
    required = schema.get("required")
    if isinstance(required, list):
        # Only keep required names we still have properties for.
        kept = [r for r in required if r in cleaned["properties"]]
        if kept:
            cleaned["required"] = kept
    return cleaned


def _normalize_tool_name(name: str) -> str:
    """Lowercase and strip separators so 'get-mail-message', 'get_mail_message'
    and 'GetMailMessage' all compare equal — config names needn't be exact."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def tool_is_allowed(tool_name: str, allowed: list[str]) -> bool:
    """Whether a bare MCP tool name passes a server's optional allowlist.

    An empty allowlist means "allow everything" (the default). Matching ignores
    case and -/_ differences so a connector that renames create_draft ->
    create-draft still matches a config that lists either spelling.
    """
    if not allowed:
        return True
    target = _normalize_tool_name(tool_name)
    return any(_normalize_tool_name(a) == target for a in allowed)


def load_mcp_config(path: Path) -> dict[str, dict]:
    """Parse mcp_servers.json -> {server_name: {command, args, env}}.

    Accepts the same shape as Claude Desktop's config ("mcpServers" key),
    so examples from the internet paste straight in.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}")
    servers = data.get("mcpServers", data)
    if not isinstance(servers, dict):
        raise ValueError(f"{path} must contain an object of servers under 'mcpServers'.")
    cleaned = {}
    for name, spec in servers.items():
        if not isinstance(spec, dict) or "command" not in spec:
            raise ValueError(f"Server '{name}' needs at least a \"command\" field.")
        # Optional per-server allowlist: keep only these tools out of everything
        # the server exposes (fewer tools = less token overhead per turn and no
        # surprise capabilities). Ignored if absent/empty. JARVIS-specific key,
        # harmlessly ignored by other MCP clients.
        allowed = spec.get("allowedTools", [])
        cleaned[name] = {
            "command": spec["command"],
            "args": spec.get("args", []),
            "env": spec.get("env", {}),
            "allowed_tools": [str(a) for a in allowed] if isinstance(allowed, list) else [],
        }
    return cleaned


class MCPManager:
    """Lazily connects to configured MCP servers and exposes their tools."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sessions: dict[str, object] = {}
        self._tools: list[dict] = []  # anthropic tool schemas, namespaced
        self._errors: dict[str, str] = {}
        self._started = False
        self._lock = threading.Lock()

    # --- lifecycle -----------------------------------------------------------
    def config_exists(self) -> bool:
        return self.cfg.mcp_config_path.exists()

    def ensure_started(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._start()

    def _start(self) -> None:
        if not self.config_exists():
            return
        try:
            servers = load_mcp_config(self.cfg.mcp_config_path)
        except ValueError as exc:
            self._errors["config"] = str(exc)
            return
        if not servers:
            return
        if not mcp_deps_ok():
            self._errors["config"] = ("MCP support needs: pip install mcp "
                                      "(then restart JARVIS)")
            return

        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever,
                         daemon=True, name="jarvis-mcp").start()
        for name, spec in servers.items():
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self._connect(name, spec), self._loop)
                fut.result(timeout=CONNECT_TIMEOUT_S)
                log.info("MCP server '%s' connected", name)
            except Exception as exc:
                self._errors[name] = f"{exc}"
                log.error("MCP server '%s' failed: %s", name, exc)

    async def _connect(self, name: str, spec: dict) -> None:
        from contextlib import AsyncExitStack

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=spec["command"],
            args=spec["args"],
            env={**os.environ, **spec["env"]},
        )
        stack = AsyncExitStack()
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        result = await session.list_tools()
        self._sessions[name] = (session, stack)
        allowed = spec.get("allowed_tools") or []
        matched: set[str] = set()
        for tool in result.tools:
            if not tool_is_allowed(tool.name, allowed):
                continue
            matched.add(_normalize_tool_name(tool.name))
            self._tools.append({
                "name": f"{name}{NAME_SEP}{tool.name}",
                "description": f"[{name} app] {tool.description or tool.name}"[:1024],
                # Some connectors (MS 365 / Graph, Canvas) ship tools whose
                # top-level schema is a union, which the Anthropic API rejects
                # and which 400s the whole turn. Normalise before sending.
                "input_schema": sanitize_input_schema(tool.inputSchema),
            })
        if allowed:
            unmatched = [a for a in allowed if _normalize_tool_name(a) not in matched]
            if unmatched:
                log.warning("MCP server '%s': %d allowedTools name(s) matched no tool "
                            "(check spelling): %s", name, len(unmatched),
                            ", ".join(unmatched))

    # --- use -------------------------------------------------------------------
    def tool_schemas(self) -> list[dict]:
        return list(self._tools)

    def call(self, full_name: str, arguments: dict) -> str:
        server_name, _, tool_name = full_name.partition(NAME_SEP)
        entry = self._sessions.get(server_name)
        if entry is None:
            return f"App '{server_name}' is not connected."
        session, _stack = entry

        async def _call():
            return await session.call_tool(tool_name, arguments or {})

        fut = asyncio.run_coroutine_threadsafe(_call(), self._loop)
        result = fut.result(timeout=CALL_TIMEOUT_S)
        parts = []
        for block in result.content:
            text = getattr(block, "text", None)
            parts.append(text if text is not None else str(block))
        out = "\n".join(parts).strip() or "(the app returned no text)"
        if getattr(result, "isError", False):
            return f"The app reported an error: {out}"
        return out

    # --- reporting ---------------------------------------------------------------
    def status_text(self) -> str:
        if not self.config_exists():
            return ("No apps configured. Copy mcp_servers.example.json to "
                    "mcp_servers.json, add your apps, and restart — see "
                    "docs/COMPUTER_AND_APPS.md for Gmail/calendar examples.")
        self.ensure_started()
        lines = ["Connected apps (MCP):"]
        if self._sessions:
            by_server: dict[str, int] = {}
            for t in self._tools:
                by_server[t["name"].split(NAME_SEP)[0]] = \
                    by_server.get(t["name"].split(NAME_SEP)[0], 0) + 1
            for name in self._sessions:
                lines.append(f"  [OK] {name} — {by_server.get(name, 0)} tool(s)")
        for name, err in self._errors.items():
            lines.append(f"  [!!] {name}: {err}")
        if len(lines) == 1:
            lines.append("  (none connected)")
        lines.append("Use them with: /agent <what you want done>")
        return "\n".join(lines)
