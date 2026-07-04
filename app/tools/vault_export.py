"""Export memory to a Markdown / Obsidian vault: /export.

Writes plain Markdown files into OBSIDIAN_VAULT (default: data/vault).
Point it at a folder inside an existing Obsidian vault and everything JARVIS
knows becomes browsable, searchable, linkable — and yours, in an open format.
Files are overwritten on each export: the database stays the source of truth,
the vault is a readable mirror.
"""

from __future__ import annotations

from pathlib import Path

from app.memory.database import Database


def _day(created_at: str) -> str:
    return (created_at or "")[:10]


def export_vault(db: Database, vault_dir: Path) -> str:
    out = Path(vault_dir).expanduser() / "JARVIS"
    out.mkdir(parents=True, exist_ok=True)

    notes = db.list_notes(limit=10_000)
    notes_md = ["# Notes", ""]
    notes_md += [f"- **{_day(r['created_at'])}** — {r['content']}" for r in notes] or ["*(none)*"]
    (out / "Notes.md").write_text("\n".join(notes_md) + "\n", encoding="utf-8")

    prefs = db.list_preferences()
    mem_md = ["# Memories", "", "Long-term facts JARVIS was asked to remember.", ""]
    mem_md += [f"- **{r['key']}**: {r['value']}" for r in prefs] or ["*(none)*"]
    (out / "Memories.md").write_text("\n".join(mem_md) + "\n", encoding="utf-8")

    tasks = db.list_tasks(include_done=True)
    tasks_md = ["# Tasks", ""]
    for r in tasks:
        box = "x" if r["done"] else " "
        due = f" (due {r['due']})" if r["due"] else ""
        tasks_md.append(f"- [{box}] {r['title']}{due}")
    if not tasks:
        tasks_md.append("*(none)*")
    (out / "Tasks.md").write_text("\n".join(tasks_md) + "\n", encoding="utf-8")

    return (f"Exported {len(notes)} note(s), {len(prefs)} memory(ies) and "
            f"{len(tasks)} task(s) to {out} — Markdown, Obsidian-ready.")
