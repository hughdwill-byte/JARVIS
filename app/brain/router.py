"""Router: decides whether input is a /command or free chat.

Also recognises a few natural phrases ("what's on my desk") so voice input
doesn't need slash syntax.
"""

from __future__ import annotations

import re

from app.brain.tool_manager import ToolManager

# Natural-language phrases that map to commands (voice-friendly).
_PHRASE_ROUTES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"\b(what'?s|what is) on my desk\b", re.I), "desk", ""),
    (re.compile(r"\btake a (photo|picture|snapshot)\b", re.I), "snapshot", ""),
    (re.compile(r"\bwhat changed (on|since)\b", re.I), "changes", ""),
    (re.compile(r"\bread (this|the) (page|document|text)\b", re.I), "read", ""),
    (re.compile(r"\bstop (talking|speaking)\b", re.I), "stop", ""),
    (re.compile(r"^(shutdown|shut down|stop listening|go to sleep)[.!]?$", re.I), "sleep", ""),
    (re.compile(r"^(start listening|wake up)[.!]?$", re.I), "listen", ""),
]


class Router:
    def __init__(self, tools: ToolManager):
        self.tools = tools

    def route(self, text: str) -> tuple[str | None, str]:
        """Return (command_name, args). command_name is None for free chat."""
        text = text.strip()
        if not text:
            return None, ""

        if text.startswith("/"):
            parts = text[1:].split(maxsplit=1)
            name = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            if self.tools.get(name):
                return name, args
            return "unknown", name

        for pattern, command, args in _PHRASE_ROUTES:
            if pattern.search(text) and self.tools.get(command):
                return command, args

        return None, text
