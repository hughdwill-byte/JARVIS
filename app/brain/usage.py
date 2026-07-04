"""LLM usage & cost tracking.

Every model call (cloud or local) is recorded in the llm_usage table:
backend, model, tokens in/out, estimated cost, latency. /usage shows the
totals, so "how much is JARVIS costing me?" has a real answer instead of a
surprise on the Anthropic invoice.

Costs are ESTIMATES from the price table below (per million tokens, standard
API list prices — prompt-caching discounts are not modelled, so real bills
are usually a bit LOWER than shown). Local Ollama models cost $0.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.memory.database import Database

# (input $/MTok, output $/MTok) by model-id prefix. First match wins.
_PRICES: list[tuple[str, float, float]] = [
    ("claude-haiku-4-5", 1.0, 5.0),
    ("claude-sonnet-5", 3.0, 15.0),
    ("claude-sonnet-4", 3.0, 15.0),
    ("claude-opus-4", 5.0, 25.0),
    ("claude-fable-5", 10.0, 50.0),
]


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    for prefix, in_price, out_price in _PRICES:
        if model.startswith(prefix):
            return (input_tokens * in_price + output_tokens * out_price) / 1_000_000
    return 0.0  # unknown/local model -> $0


class UsageTracker:
    def __init__(self, db: "Database"):
        self.db = db

    def record(self, backend: str, model: str, input_tokens: int,
               output_tokens: int, latency_ms: int) -> None:
        try:
            self.db.add_usage(backend, model, int(input_tokens or 0),
                              int(output_tokens or 0),
                              estimate_cost(model, input_tokens or 0, output_tokens or 0),
                              int(latency_ms))
        except Exception:  # tracking must never break a reply
            pass

    def summary_text(self) -> str:
        now = datetime.now(timezone.utc)
        lines = ["LLM usage (estimated; caching discounts not counted):"]
        for label, days in (("Today", 1), ("Last 7 days", 7), ("Last 30 days", 30)):
            since = (now - timedelta(days=days)).isoformat(timespec="seconds")
            rows = self.db.usage_since(since)
            if not rows:
                lines.append(f"  {label}: no LLM calls.")
                continue
            total = sum(r["cost_usd"] or 0 for r in rows)
            calls = sum(r["calls"] for r in rows)
            lines.append(f"  {label}: {calls} call(s), ~${total:.2f}")
            for r in rows:
                cost = r["cost_usd"] or 0
                cost_s = "free (local)" if r["backend"] == "ollama" else f"~${cost:.2f}"
                lines.append(
                    f"    - {r['model']}: {r['calls']} call(s), "
                    f"{(r['input_tokens'] or 0):,} in / {(r['output_tokens'] or 0):,} out, "
                    f"{cost_s}"
                )
        return "\n".join(lines)


# Global hook so LLM clients can record without threading a tracker through
# every constructor. Assistant.__init__ sets it; None = tracking off (tests).
TRACKER: UsageTracker | None = None


def set_tracker(tracker: UsageTracker | None) -> None:
    global TRACKER
    TRACKER = tracker


def record(backend: str, model: str, input_tokens: int, output_tokens: int,
           latency_ms: int) -> None:
    if TRACKER is not None:
        TRACKER.record(backend, model, input_tokens, output_tokens, latency_ms)
