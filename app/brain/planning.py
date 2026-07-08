"""Task decomposition + lightweight context compaction for long agent runs.

Patterns adapted (reimplemented — NO code copied) from OpenJarvis
(https://github.com/open-jarvis/OpenJarvis), Apache-2.0:

- Explicit up-front task decomposition before acting — idea from
  agents/manager.py and agents/executor.py (plan, then execute steps).
- Defensive JSON-or-lines parsing of model output that never raises — idea
  from memory/extractor.py (FactExtractor._coerce_to_list / _clean_fact).
- Token-budget context compaction that elides stale tool observations — idea
  from agents/hybrid/mini_swe_agent.py (_estimate_prompt_tokens and
  _compact_local_messages "stage 1" tool-output elision).

Only the ideas are borrowed. This is a compact, self-contained module that
speaks JARVIS's own message shapes and plugs into the existing Agent loop and
safety model — no registries, no event bus, no framework.
"""

from __future__ import annotations

import json
import re

from app.logger import get_logger

log = get_logger("planning")

# Keep planning cheap and terse: a handful of concrete steps, no prose.
_PLAN_SYSTEM = (
    "You are the planning step of an AI agent. Given a task the agent must "
    "carry out on the user's computer and connected apps, break it into a "
    "short ordered list of concrete steps (look before you touch: inspect "
    "before changing). Be terse and practical.\n\n"
    "Respond with ONLY a JSON array of short step strings (each under 120 "
    "characters). No preamble, no numbering, no commentary. If the task is a "
    "single trivial action, respond with a one-element array."
)


# --- task decomposition -------------------------------------------------------

def parse_steps(content: str, max_steps: int = 6) -> list[str]:
    """Parse model output into a clean, deduped, capped list of step strings.

    Tolerant of the ways small models wrap output: a JSON array anywhere in the
    text, or markdown bullets / numbered lines as a fallback. Never raises.
    """
    if not content or not content.strip():
        return []
    raw = _coerce_to_list(content)
    steps: list[str] = []
    seen: set[str] = set()
    for item in raw:
        step = _clean_step(item)
        if not step:
            continue
        key = step.lower()
        if key in seen:
            continue
        seen.add(key)
        steps.append(step)
        if len(steps) >= max_steps:
            break
    return steps


def _coerce_to_list(content: str) -> list[str]:
    # Prefer a JSON array anywhere in the text (models wrap it in prose/fences).
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except (json.JSONDecodeError, ValueError):
            pass
    # Fall back to line-based parsing (bullets / "1." / "1)" prefixes).
    items: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line)
        if line:
            items.append(line)
    return items


def _clean_step(item: str) -> str:
    step = str(item).strip().strip("\"'").strip()
    if not step or step.lower() in ("[]", "none", "n/a", "null"):
        return ""
    return step[:200].rstrip()


def plan_steps(llm, task: str, model: str, max_steps: int = 6,
               max_tokens: int = 512) -> list[str]:
    """Ask the model for a short ordered plan for ``task``.

    Best-effort and defensive: returns ``[]`` on a missing client, an API
    failure, or unparseable output — planning must never break the agent run.
    Uses the raw Anthropic client so it works with the same fake-client test
    seam the tool loop uses.
    """
    task = (task or "").strip()
    if not task:
        return []
    client = getattr(llm, "raw", None)
    if client is None:
        return []
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": _PLAN_SYSTEM}],
            messages=[{"role": "user", "content": f"Task: {task}"}],
        )
    except Exception:  # noqa: BLE001 — planning is best-effort
        log.debug("Planning call failed; continuing without a plan", exc_info=True)
        return []
    content = "".join(
        getattr(b, "text", "") for b in getattr(resp, "content", [])
        if getattr(b, "type", None) == "text"
    )
    return parse_steps(content, max_steps)


# --- lightweight context compaction ------------------------------------------

def estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate for a message list (len//4 heuristic, no tokenizer).

    Handles both plain-string content and the block-list content the agent loop
    uses for assistant tool_use / user tool_result messages.
    """
    total = 0
    for m in messages:
        total += 4  # per-message overhead
        content = m.get("content")
        if isinstance(content, str):
            total += len(content) // 4
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("content") or block.get("text") or ""
                    if not isinstance(text, str):
                        text = str(text)
                    total += len(text) // 4
                else:  # SDK content block object
                    total += len(getattr(block, "text", "") or "") // 4
    return total


def _is_observation(message: dict) -> bool:
    """A user message carrying at least one tool_result block."""
    content = message.get("content")
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    )


def compact_messages(messages: list[dict], *, cap_tokens: int = 12000,
                     keep_last: int = 3, stub_over: int = 200) -> list[dict]:
    """Elide stale tool observations when the transcript grows past ``cap_tokens``.

    Keeps the conversation well-formed (every tool_use keeps its matching
    tool_result, so ids never dangle) but replaces the *content* of old, long
    tool results with a short stub. The most recent ``keep_last`` observation
    messages are always left intact. Returns a new list; never mutates the
    input. A no-op below the cap (so normal short runs are untouched).
    """
    if cap_tokens <= 0 or estimate_tokens(messages) <= cap_tokens:
        return messages

    obs_indices = [i for i, m in enumerate(messages) if _is_observation(m)]
    if len(obs_indices) <= keep_last:
        return messages
    elide_before = obs_indices[-keep_last] if keep_last > 0 else len(messages)

    out: list[dict] = []
    n_elided = 0
    for i, m in enumerate(messages):
        if i >= elide_before or not _is_observation(m):
            out.append(m)
            continue
        new_content = []
        for block in m["content"]:
            if (isinstance(block, dict) and block.get("type") == "tool_result"
                    and isinstance(block.get("content"), str)
                    and len(block["content"]) > stub_over):
                n_elided += 1
                new_content.append({
                    **block,
                    "content": f"[earlier tool output elided: {len(block['content'])} chars]",
                })
            else:
                new_content.append(block)
        out.append({**m, "content": new_content})

    if n_elided:
        log.debug("Compacted agent context: elided %d stale tool result(s) "
                  "(~%d -> ~%d tokens)", n_elided,
                  estimate_tokens(messages), estimate_tokens(out))
    return out
