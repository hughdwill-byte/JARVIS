"""Proactive assistant: the "you should know…" nudges a movie JARVIS volunteers.

Surfaces things worth flagging *without being asked* — currently stale open
tasks — but under strict, user-controlled limits so it never becomes nagware:

- Do Not Disturb (`/dnd`): silences all volunteered messages entirely.
- Notification budget: at most `notify_budget` nudges per check.
- Throttle: automatic check-ins fire at most once per `proactive_interval_s`,
  tracked in the database so a restart doesn't reset the quiet period.

`/checkin` asks for a summary on demand — that's the user talking, not JARVIS
volunteering, so it bypasses the throttle, the budget, and DND.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.config import Config

if TYPE_CHECKING:
    from app.memory.database import Database

_LAST_RUN_KEY = "proactive_last_run"


class ProactiveMonitor:
    def __init__(self, cfg: Config, db: "Database"):
        self.cfg = cfg
        self.db = db

    def checkins(self, force: bool = False) -> list[str]:
        """Return volunteered messages. `force` (from /checkin) bypasses DND,
        the enabled flag, the throttle and the budget — it's an explicit ask."""
        if not force:
            if self.cfg.do_not_disturb or not self.cfg.proactive_enabled:
                return []
            if not self._due_for_run():
                return []

        messages = self._gather()

        if not force:
            self._mark_run()  # only automatic runs consume the quiet period
            messages = messages[: max(0, self.cfg.notify_budget)]
        return messages

    def summary_text(self) -> str:
        """For /checkin: always answers, even when there's nothing to flag."""
        msgs = self.checkins(force=True)
        if not msgs:
            return "Nothing needs your attention right now. All quiet."
        return "\n".join(msgs)

    # --- checks -------------------------------------------------------------
    def _gather(self) -> list[str]:
        out = []
        stale = self._stale_tasks()
        if stale:
            titles = ", ".join(f"\"{t}\"" for t in stale[:3])
            more = f" (and {len(stale) - 3} more)" if len(stale) > 3 else ""
            n = len(stale)
            out.append(
                f"Heads up — {n} task{'s' if n != 1 else ''} "
                f"{'have' if n != 1 else 'has'} been open more than "
                f"{self.cfg.stale_task_days} days: {titles}{more}. "
                "Worth finishing or dropping?"
            )
        return out

    def _stale_tasks(self) -> list[str]:
        now = datetime.now(timezone.utc)
        stale = []
        for r in self.db.list_tasks():  # open tasks only
            created = self._parse(r["created_at"])
            if created is None:
                continue
            if (now - created).days >= self.cfg.stale_task_days:
                stale.append(r["title"])
        return stale

    @staticmethod
    def _parse(iso: str | None) -> datetime | None:
        if not iso:
            return None
        try:
            dt = datetime.fromisoformat(iso)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    # --- throttle (persisted) ----------------------------------------------
    def _due_for_run(self) -> bool:
        last = self._parse(self.db.get_preference(_LAST_RUN_KEY))
        if last is None:
            return True
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= self.cfg.proactive_interval_s

    def _mark_run(self) -> None:
        self.db.set_preference(
            _LAST_RUN_KEY, datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
