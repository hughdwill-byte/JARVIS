"""Turn model output into text that *sounds* right when read aloud.

The LLM's replies are written for the eye: markdown emphasis (`**bold**`),
bullet symbols, backtick'd code, links, and abbreviations like "e.g." / "etc."
A raw TTS engine reads those literally — "star star", "backtick", "e g" — which
sounds broken. This module strips the visual markup and expands the common
abbreviations to what a person would actually *say*, so the spoken version is
clean while the on-screen text stays untouched.

Applied once, at synthesis time, so every backend (Kokoro, piper, say, pyttsx3)
benefits.
"""

from __future__ import annotations

import re

# Abbreviation -> spoken form. Matched case-insensitively, optional trailing dot.
# Only the ones TTS engines routinely mangle (spell out or mispronounce).
_ABBREVIATIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\be\.g\.?", re.I), "for example"),
    (re.compile(r"\bi\.e\.?", re.I), "that is"),
    (re.compile(r"\ba\.k\.a\.?", re.I), "also known as"),
    (re.compile(r"\betc\.?", re.I), "and so on"),
    (re.compile(r"\bvs\.?", re.I), "versus"),
    (re.compile(r"\bapprox\.?", re.I), "approximately"),
    (re.compile(r"\bw/o\b", re.I), "without"),
    (re.compile(r"\bw/\b", re.I), "with"),
]

_LINK_MD = re.compile(r"\[([^\]]+)\]\([^)]+\)")      # [label](url) -> label
_BARE_URL = re.compile(r"https?://\S+")              # raw URL -> "link"
_BULLET = re.compile(r"(?m)^[ \t]*[-+*•]\s+")        # list markers at line start
_MD_SYMBOLS = re.compile(r"[`*_#>|~]")               # emphasis / code / heading marks
_MULTISPACE = re.compile(r"[ \t]*\n[ \t]*|\s{2,}")


def to_speech_text(text: str) -> str:
    """Return a spoken-friendly version of `text` (markdown stripped,
    abbreviations expanded). Safe on empty/plain input."""
    if not text or not text.strip():
        return ""
    t = _LINK_MD.sub(r"\1", text)
    t = _BARE_URL.sub("link", t)
    t = t.replace("```", " ")           # fence lines -> space (keep the words)
    t = _BULLET.sub("", t)              # drop "- " / "* " list markers
    t = _MD_SYMBOLS.sub("", t)          # drop *, _, `, #, >, |, ~
    for pattern, spoken in _ABBREVIATIONS:
        t = pattern.sub(spoken, t)
    t = t.replace("&", " and ")
    t = re.sub(r"(\d)\s*%", r"\1 percent", t)   # "50%" -> "50 percent"
    t = _MULTISPACE.sub(" ", t)
    return t.strip()
