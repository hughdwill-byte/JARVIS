"""SQLite storage for everything the assistant remembers.

One small database, plain SQL, no ORM. Tables:
  notes         — free-form notes the user asked to save
  tasks         — task list with done/undone state
  reminders     — time-based reminders
  preferences   — long-term facts the user approved storing
  conversation  — rolling chat history (context for the LLM)
  scenes        — desk snapshot summaries + object inventories
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    title TEXT NOT NULL,
    due TEXT,
    done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    remind_at TEXT NOT NULL,
    message TEXT NOT NULL,
    fired INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    image_path TEXT,
    summary TEXT NOT NULL,
    objects TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # dashboard + assistant may share this
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # --- notes ---------------------------------------------------
    def add_note(self, content: str) -> int:
        cur = self._execute(
            "INSERT INTO notes (created_at, content) VALUES (?, ?)", (_now(), content)
        )
        return cur.lastrowid

    def list_notes(self, limit: int = 20) -> list[sqlite3.Row]:
        return self._query(
            "SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,)
        )

    def delete_note(self, note_id: int) -> bool:
        return self._execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount > 0

    # --- tasks ---------------------------------------------------
    def add_task(self, title: str, due: str | None = None) -> int:
        cur = self._execute(
            "INSERT INTO tasks (created_at, title, due) VALUES (?, ?, ?)",
            (_now(), title, due),
        )
        return cur.lastrowid

    def list_tasks(self, include_done: bool = False) -> list[sqlite3.Row]:
        if include_done:
            return self._query("SELECT * FROM tasks ORDER BY done, id")
        return self._query("SELECT * FROM tasks WHERE done = 0 ORDER BY id")

    def complete_task(self, task_id: int) -> bool:
        return self._execute(
            "UPDATE tasks SET done = 1 WHERE id = ?", (task_id,)
        ).rowcount > 0

    def delete_task(self, task_id: int) -> bool:
        return self._execute("DELETE FROM tasks WHERE id = ?", (task_id,)).rowcount > 0

    # --- reminders -----------------------------------------------
    def add_reminder(self, remind_at: str, message: str) -> int:
        cur = self._execute(
            "INSERT INTO reminders (created_at, remind_at, message) VALUES (?, ?, ?)",
            (_now(), remind_at, message),
        )
        return cur.lastrowid

    def due_reminders(self, now_iso: str | None = None) -> list[sqlite3.Row]:
        return self._query(
            "SELECT * FROM reminders WHERE fired = 0 AND remind_at <= ? ORDER BY remind_at",
            (now_iso or _now(),),
        )

    def list_reminders(self) -> list[sqlite3.Row]:
        return self._query("SELECT * FROM reminders WHERE fired = 0 ORDER BY remind_at")

    def mark_reminder_fired(self, reminder_id: int) -> None:
        self._execute("UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,))

    # --- preferences ----------------------------------------------
    def set_preference(self, key: str, value: str) -> None:
        self._execute(
            "INSERT INTO preferences (created_at, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_now(), key, value),
        )

    def get_preference(self, key: str) -> str | None:
        rows = self._query("SELECT value FROM preferences WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    def list_preferences(self) -> list[sqlite3.Row]:
        return self._query("SELECT * FROM preferences ORDER BY key")

    def delete_preference(self, key: str) -> bool:
        return self._execute(
            "DELETE FROM preferences WHERE key = ?", (key,)
        ).rowcount > 0

    # --- conversation ---------------------------------------------
    def add_message(self, role: str, content: str) -> None:
        self._execute(
            "INSERT INTO conversation (created_at, role, content) VALUES (?, ?, ?)",
            (_now(), role, content),
        )

    def recent_messages(self, limit: int = 12) -> list[dict]:
        rows = self._query(
            "SELECT role, content FROM conversation ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear_conversation(self) -> None:
        self._execute("DELETE FROM conversation")

    # --- scenes ----------------------------------------------------
    def add_scene(self, summary: str, objects: str, image_path: str | None = None) -> int:
        cur = self._execute(
            "INSERT INTO scenes (created_at, image_path, summary, objects) VALUES (?, ?, ?, ?)",
            (_now(), image_path, summary, objects),
        )
        return cur.lastrowid

    def recent_scenes(self, limit: int = 5) -> list[sqlite3.Row]:
        return self._query("SELECT * FROM scenes ORDER BY id DESC LIMIT ?", (limit,))
