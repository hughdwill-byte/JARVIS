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
    (re.compile(r"^(good morning|morning)[,.!]?( jarvis)?[.!]?$", re.I), "briefing", ""),
    (re.compile(r"\b(morning|daily) briefing\b", re.I), "briefing", ""),
    # "$REST" = pass whatever follows the matched prefix as the command args,
    # e.g. "search my notes about thermo" -> /ask about thermo.
    (re.compile(r"^(search|check|ask) my notes\b[:,]?\s*", re.I), "ask", "$REST"),
]


# Requests that clearly need the computer or a connected app. Used by the
# claude_code backend (whose plain chat has no tools) to route such requests to
# agent mode automatically — no /agent needed. Free to evaluate (no LLM call);
# a miss just falls through to plain chat, and /agent still forces it.
_COMPUTER_TASK_HINTS: list[re.Pattern] = [re.compile(p, re.I) for p in (
    r"\bmy (email|emails|inbox|mail|calendar|schedule)\b",
    r"\bmy (downloads|desktop|documents|files|folders?|drive)\b",
    r"\b(tidy|organi[sz]e|clean up|sort( out)?|rename|move|copy)\b.{0,40}"
    r"\b(folder|files?|downloads|desktop|photos?)\b",
    r"\b(create|make|write|save|start)\b.{0,40}"
    r"\b(file|folder|document|spreadsheet|word doc|docx?|pdf|csv)\b",
    r"\brun (a |the |this )?(command|script)\b",
    r"\bopen\b.{0,40}\b(app|application|browser|website|folder|file)\b",
    r"\b(send|draft|reply to)\b.{0,40}\b(email|mail|message)\b",
    r"\bon (this|my) (computer|machine|mac|pc|laptop)\b",
    r"\bfind\b.{0,60}\b(files?|pdfs?|folders?|photos?|documents?)\b",
)]


def looks_like_computer_task(text: str) -> bool:
    """True when a chat message plainly needs files/commands/apps to answer."""
    return any(p.search(text) for p in _COMPUTER_TASK_HINTS)


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
            m = pattern.search(text)
            if m and self.tools.get(command):
                if args == "$REST":
                    return command, text[m.end():].strip()
                return command, args

        return None, text
