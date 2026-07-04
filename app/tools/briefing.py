"""Morning briefing: /briefing, or just say "good morning".

Assembled locally from the database — no LLM call, so it's free, instant,
and works offline. Spoken-style output because it's usually heard, not read.
"""

from __future__ import annotations

from datetime import datetime

from app.memory.database import Database

_MAX_TASKS = 6
_MAX_NOTES = 2


def build_briefing(db: Database) -> str:
    now = datetime.now()
    lines = [f"Good morning. It's {now:%A, %B %d}."]

    tasks = db.list_tasks()
    if tasks:
        dued = [r for r in tasks if r["due"]]
        headline = f"You have {len(tasks)} open task{'s' if len(tasks) != 1 else ''}"
        headline += f", {len(dued)} with a due date." if dued else "."
        lines.append(headline)
        for r in tasks[:_MAX_TASKS]:
            due = f" — due {r['due']}" if r["due"] else ""
            lines.append(f"  • {r['title']}{due}")
        if len(tasks) > _MAX_TASKS:
            lines.append(f"  …and {len(tasks) - _MAX_TASKS} more (see /tasks).")
    else:
        lines.append("No open tasks. A rare and beautiful sight.")

    pending = [r for r in db.list_reminders() if not r["fired"]]
    if pending:
        lines.append(f"{len(pending)} reminder{'s' if len(pending) != 1 else ''} pending:")
        for r in pending[:3]:
            when = r["remind_at"][:16].replace("T", " ")
            lines.append(f"  • {when} UTC: {r['message']}")

    notes = db.list_notes(_MAX_NOTES)
    if notes:
        latest = notes[0]["content"]
        snippet = latest if len(latest) <= 80 else latest[:77] + "…"
        lines.append(f"Your latest note: \"{snippet}\"")

    lines.append("That's the state of things.")
    return "\n".join(lines)
