"""Long-term preferences — stored only with explicit user approval.

The assistant never writes here on its own; the user drives it via
/remember, /memories, /forget so memory stays fully under their control.
"""

from __future__ import annotations

from app.memory.database import Database


class Preferences:
    def __init__(self, db: Database):
        self.db = db

    def remember(self, text: str) -> str:
        """Store 'key: value' or plain text (keyed by its first few words)."""
        text = text.strip()
        if not text:
            return "Tell me what to remember. Try: /remember I prefer metric units"
        if ":" in text:
            key, _, value = text.partition(":")
            key, value = key.strip(), value.strip()
        else:
            words = text.split()
            key, value = " ".join(words[:4]).lower(), text
        self.db.set_preference(key, value)
        return f"Remembered — \"{key}\": {value}. Use /forget {key} to remove it."

    def list_text(self) -> str:
        rows = self.db.list_user_preferences()
        if not rows:
            return "I haven't stored any long-term memories. Use /remember <fact> to add one."
        lines = [f"- {r['key']}: {r['value']}" for r in rows]
        return "Things you've asked me to remember:\n" + "\n".join(lines)

    def as_context(self, limit: int = 10) -> list[str]:
        return [f"{r['key']}: {r['value']}" for r in self.db.list_user_preferences()[:limit]]

    def forget(self, key: str) -> str:
        key = key.strip()
        if self.db.delete_preference(key):
            return f"Forgotten: {key}."
        return f"I don't have a memory keyed \"{key}\". Use /memories to see what's stored."
