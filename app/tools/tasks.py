"""Task list tool: /task, /tasks, /done, /deltask."""

from __future__ import annotations

import re

from app.memory.database import Database

_DUE_RE = re.compile(r"\bdue\s+(.+)$", re.I)


class TaskManager:
    def __init__(self, db: Database):
        self.db = db

    def add(self, text: str) -> str:
        text = text.strip()
        if not text:
            return "What's the task? Try: /task finish lab report due friday"
        due = None
        m = _DUE_RE.search(text)
        if m:
            due = m.group(1).strip()
            text = text[: m.start()].strip()
        task_id = self.db.add_task(text, due)
        suffix = f" (due {due})" if due else ""
        return f"Task #{task_id} added: {text}{suffix}"

    def list_text(self) -> str:
        rows = self.db.list_tasks()
        if not rows:
            return "Task list is empty. Enjoy it while it lasts."
        lines = []
        for r in rows:
            due = f"  [due {r['due']}]" if r["due"] else ""
            lines.append(f"#{r['id']}: {r['title']}{due}")
        return "Open tasks:\n" + "\n".join(lines)

    def open_titles(self, limit: int = 10) -> list[str]:
        return [r["title"] for r in self.db.list_tasks()[:limit]]

    def complete(self, arg: str) -> str:
        try:
            task_id = int(arg.strip().lstrip("#"))
        except ValueError:
            return "Give me the task number, e.g. /done 3 (see /tasks for numbers)."
        if self.db.complete_task(task_id):
            return f"Task #{task_id} done. Nice."
        return f"No open task #{task_id}. Check /tasks."

    def delete(self, arg: str) -> str:
        try:
            task_id = int(arg.strip().lstrip("#"))
        except ValueError:
            return "Give me the task number, e.g. /deltask 3."
        if self.db.delete_task(task_id):
            return f"Task #{task_id} deleted."
        return f"No task #{task_id} found."
