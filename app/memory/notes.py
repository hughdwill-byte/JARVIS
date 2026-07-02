"""User notes: thin, friendly layer over the notes table."""

from __future__ import annotations

from app.memory.database import Database


class Notes:
    def __init__(self, db: Database):
        self.db = db

    def add(self, content: str) -> str:
        content = content.strip()
        if not content:
            return "I need some text to save. Try: /note buy a longer USB cable"
        note_id = self.db.add_note(content)
        return f"Noted (#{note_id}): {content}"

    def list_text(self, limit: int = 10) -> str:
        rows = self.db.list_notes(limit)
        if not rows:
            return "No notes saved yet. Use /note <text> to add one."
        lines = [f"#{r['id']} ({r['created_at'][:10]}): {r['content']}" for r in rows]
        return "Your notes:\n" + "\n".join(lines)

    def recent_contents(self, limit: int = 5) -> list[str]:
        return [r["content"] for r in self.db.list_notes(limit)]

    def delete(self, note_id: int) -> str:
        if self.db.delete_note(note_id):
            return f"Deleted note #{note_id}."
        return f"No note with id {note_id}. Use /notes to see the list."
