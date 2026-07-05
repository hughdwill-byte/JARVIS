"""Security layer: secret redaction + tool-call audit log.

Two independent safety nets for an assistant that has file, shell, and
connected-app access:

1. redact() / RedactionFilter — scrub API keys, tokens, bearer credentials,
   passwords and email addresses out of anything written to the logs. JARVIS
   reads emails and runs commands; a stray key or address must never end up in
   a plaintext log file that gets shared while debugging.

2. AuditLog — an append-only record of every tool the agent runs (executed,
   declined, or errored), with the arguments already redacted. `/audit` shows
   it, so there's always an answer to "what did it actually do on my machine?"

Kept dependency-free (stdlib + the existing SQLite database).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.memory.database import Database

# Order matters: specific credential shapes first, generic key=value last, then
# emails. Each entry is (compiled pattern, replacement).
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"), "[redacted:anthropic-key]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "[redacted:api-key]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "[redacted:github-token]"),
    (re.compile(r"\bhf_[A-Za-z0-9]{20,}"), "[redacted:hf-token]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"), "[redacted:slack-token]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{10,}"), "Bearer [redacted]"),
    # key=value / key: value secrets — keep the key name, hide the value.
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password|passwd|pwd)"
                r"(\s*[=:]\s*)(\"?)([^\s\"',]+)"),
     r"\1\2\3[redacted]"),
]

# Emails handled separately so we can keep the domain (debuggable) but hide the
# local part: alice@example.com -> [redacted]@example.com.
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})")


def redact(text: str) -> str:
    """Return text with secrets and email local-parts masked. Never raises."""
    if not text:
        return text
    try:
        for pattern, repl in _RULES:
            text = pattern.sub(repl, text)
        text = _EMAIL.sub(r"[redacted]@\1", text)
    except Exception:
        return text
    return text


class RedactionFilter:
    """A logging.Filter that redacts the fully-formatted message. Installed on
    every handler so no sensitive value reaches a log line."""

    def filter(self, record) -> bool:  # logging.Filter interface
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:
            pass
        return True


class AuditLog:
    """Append-only tool-call record, stored in the main database."""

    VALID_OUTCOMES = ("executed", "declined", "error")

    def __init__(self, db: "Database"):
        self.db = db

    def record(self, tool: str, description: str, outcome: str,
               detail: str = "") -> None:
        try:
            self.db.add_audit(tool, redact(description),
                              outcome if outcome in self.VALID_OUTCOMES else "executed",
                              redact(detail)[:500])
        except Exception:  # auditing must never break the action it records
            pass

    def summary_text(self, limit: int = 20) -> str:
        rows = self.db.recent_audit(limit)
        if not rows:
            return ("No tool actions recorded yet. When JARVIS uses your computer "
                    "or apps (files, commands, email…), every action is logged here.")
        icon = {"executed": "✓", "declined": "✗", "error": "!"}
        lines = [f"Recent tool actions (newest first, up to {limit}):"]
        for r in rows:
            when = (r["created_at"] or "")[:16].replace("T", " ")
            mark = icon.get(r["outcome"], "?")
            line = f"  {mark} {when}  {r['description']}"
            if r["outcome"] == "error" and r["detail"]:
                line += f"  — {r['detail'][:80]}"
            lines.append(line)
        return "\n".join(lines)


# Global audit hook, mirroring usage/latency, so the agent records without
# threading an object through every constructor. Assistant sets it.
AUDIT: AuditLog | None = None


def set_audit(audit: AuditLog | None) -> None:
    global AUDIT
    AUDIT = audit


def record_tool_call(tool: str, description: str, outcome: str, detail: str = "") -> None:
    if AUDIT is not None:
        AUDIT.record(tool, description, outcome, detail)
