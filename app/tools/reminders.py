"""Reminders: '/remind 20m stretch', '/remind 2h check the oven'.

Checked opportunistically each time the assistant loop ticks, and every
few seconds by the dashboard. Simple by design — no background daemon.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.memory.database import Database

_SPAN_RE = re.compile(r"^(\d+)\s*(m|min|mins|minutes|h|hr|hrs|hours|s|sec|secs|seconds)\b", re.I)


def parse_delay(text: str) -> tuple[timedelta | None, str]:
    """Parse a leading '20m' / '2h' style delay; return (delta, remaining_message)."""
    m = _SPAN_RE.match(text.strip())
    if not m:
        return None, text.strip()
    value = int(m.group(1))
    unit = m.group(2).lower()[0]
    delta = {"s": timedelta(seconds=value),
             "m": timedelta(minutes=value),
             "h": timedelta(hours=value)}[unit]
    return delta, text.strip()[m.end():].strip()


class ReminderManager:
    def __init__(self, db: Database):
        self.db = db

    def add(self, text: str) -> str:
        delta, message = parse_delay(text)
        if delta is None:
            return ("Format: /remind <delay> <message> — e.g. /remind 25m take a break, "
                    "/remind 2h submit the form")
        if not message:
            message = "you set a reminder"
        remind_at = datetime.now(timezone.utc) + delta
        self.db.add_reminder(remind_at.isoformat(timespec="seconds"), message)
        local = (datetime.now() + delta).strftime("%H:%M")
        return f"Reminder set for ~{local}: {message}"

    def list_text(self) -> str:
        rows = self.db.list_reminders()
        if not rows:
            return "No pending reminders."
        lines = [f"#{r['id']} at {r['remind_at'][:16].replace('T', ' ')} UTC: {r['message']}"
                 for r in rows]
        return "Pending reminders:\n" + "\n".join(lines)

    def pop_due(self) -> list[str]:
        """Return messages for reminders that are due, marking them fired."""
        due = self.db.due_reminders()
        messages = []
        for r in due:
            self.db.mark_reminder_fired(r["id"])
            messages.append(r["message"])
        return messages
