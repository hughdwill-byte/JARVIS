"""Scene memory: remembers what was on the desk and answers 'what changed?'.

Stores only text (summary + object inventory) in SQLite — images themselves
are pruned per the retention setting, so long-term memory never keeps photos.
"""

from __future__ import annotations

from app.memory.database import Database


def _normalize(objects_csv: str) -> set[str]:
    return {
        o.strip().lower().lstrip("(").rstrip(")")
        for o in objects_csv.split(",")
        if o.strip()
    }


def diff_objects(earlier_csv: str, now_csv: str) -> tuple[list[str], list[str]]:
    """Return (added, removed) object lists between two inventories."""
    earlier, now = _normalize(earlier_csv), _normalize(now_csv)
    return sorted(now - earlier), sorted(earlier - now)


class SceneMemory:
    def __init__(self, db: Database):
        self.db = db

    def record(self, summary: str, objects_csv: str, image_path: str | None = None) -> int:
        return self.db.add_scene(summary, objects_csv, image_path)

    def latest_summary(self) -> str | None:
        scenes = self.db.recent_scenes(1)
        return scenes[0]["summary"] if scenes else None

    def describe_changes(self) -> str:
        """Compare the two most recent scenes as plain text (no API needed)."""
        scenes = self.db.recent_scenes(2)
        if not scenes:
            return "No desk snapshots recorded yet. Use /desk to take the first one."
        if len(scenes) < 2:
            return ("I only have one desk snapshot on record — take another with "
                    "/desk later and I can tell you what changed.")
        now, earlier = scenes[0], scenes[1]
        added, removed = diff_objects(earlier["objects"], now["objects"])
        if not added and not removed:
            return "Nothing meaningful has changed on your desk since the last snapshot."
        parts = []
        if added:
            parts.append("appeared: " + ", ".join(added))
        if removed:
            parts.append("gone: " + ", ".join(removed))
        return f"Since {earlier['created_at'][:16].replace('T', ' ')} — " + "; ".join(parts) + "."

    def history_text(self, limit: int = 5) -> str:
        scenes = self.db.recent_scenes(limit)
        if not scenes:
            return "No desk snapshots recorded yet. Use /desk to take and analyse one."
        lines = [
            f"[{s['created_at'][:16].replace('T', ' ')}] {s['summary'][:120]}"
            for s in scenes
        ]
        return "Recent desk snapshots:\n" + "\n".join(lines)
