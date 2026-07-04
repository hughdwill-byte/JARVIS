"""Local text embeddings via Ollama — the engine behind RAG (/ask).

Embeddings turn text into vectors so JARVIS can find the notes/vault passages
most relevant to a question, instead of stuffing everything into the prompt.
This runs on the SAME local Ollama server as the chat model (free, private,
offline) and uses only the standard library — no torch, no vector-DB package.

Model: nomic-embed-text (default) — small, fast, good quality. Install once:
`ollama pull nomic-embed-text`. Any Ollama embedding model works via EMBED_MODEL.
"""

from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.request

from app.config import Config
from app.logger import get_logger

log = get_logger("embed")

_PING_TTL_S = 30
_CHUNK_CHARS = 700       # ~150 words per chunk: enough context, cheap to embed
_CHUNK_OVERLAP = 100     # carry a little context across chunk boundaries

EMBED_MISSING = (
    "Local embeddings need Ollama and an embedding model. Install Ollama "
    "(https://ollama.com), run `ollama pull {model}`, make sure it's running, "
    "then try again. (This powers /ask and /index; it's free and fully local.)"
)


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors (0 if either is empty/zero)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def chunk_text(text: str, size: int = _CHUNK_CHARS,
               overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks on paragraph/sentence-ish boundaries."""
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # prefer to break at a paragraph, then sentence, then space
            window = text[start:end]
            for sep in ("\n\n", ". ", "\n", " "):
                cut = window.rfind(sep)
                if cut > size // 2:
                    end = start + cut + len(sep)
                    break
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


class Embedder:
    """Talks to Ollama's /api/embeddings. Availability is cached like the chat
    client so a down server is retried, not hammered."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._ping_ok: bool | None = None
        self._ping_at: float = 0.0

    @property
    def available(self) -> bool:
        now = time.monotonic()
        if self._ping_ok is True:
            return True
        if self._ping_ok is False and now - self._ping_at < _PING_TTL_S:
            return False
        self._ping_ok = self._ping()
        self._ping_at = now
        return self._ping_ok

    def _ping(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.cfg.ollama_host}/api/tags",
                                        timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def setup_help(self) -> str:
        return EMBED_MISSING.format(model=self.cfg.embed_model)

    def embed(self, text: str) -> list[float] | None:
        """Embed one string. None on any failure (caller degrades gracefully)."""
        payload = {"model": self.cfg.embed_model, "prompt": text}
        try:
            req = urllib.request.Request(
                f"{self.cfg.ollama_host}/api/embeddings",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.cfg.ollama_timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            vec = data.get("embedding")
            return vec if isinstance(vec, list) and vec else None
        except urllib.error.HTTPError as exc:
            self._ping_ok = None
            body = ""
            try:
                body = exc.read().decode("utf-8")[:150]
            except Exception:
                pass
            log.error("Embedding HTTP %s: %s", exc.code, body)
            return None
        except Exception as exc:
            self._ping_ok = None
            log.error("Embedding failed: %s", exc)
            return None
