"""Personal knowledge base: RAG over your notes, memories and Obsidian vault.

`/index` embeds everything JARVIS knows (saved notes, long-term memories, and
Markdown files in your vault) into the local `knowledge` table. `/ask` embeds
your question, finds the most similar passages by cosine similarity, and has the
brain answer **using only those passages, with [n] citations** — so it draws on
*your* material and tells you when the answer isn't there instead of guessing.

Everything is local and free: embeddings run on Ollama, similarity is computed
here, storage is the same SQLite database. Nothing leaves the machine to build
or search the index. (The final answer uses whatever brain you've configured —
local or cloud — via the normal chat path.)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from app.brain.embeddings import Embedder, chunk_text, cosine
from app.config import Config
from app.logger import get_logger

if TYPE_CHECKING:
    from app.memory.database import Database

log = get_logger("rag")

_TOP_K = 4
_MIN_SCORE = 0.35          # below this, a "match" is probably noise
_MAX_VAULT_FILES = 500     # safety cap for a huge vault
_MAX_FILE_BYTES = 1_000_000

RAG_INSTRUCTION = (
    "You are answering from the user's own saved notes and files. Use ONLY the "
    "numbered sources below. Cite the sources you use like [1], [2]. If the "
    "answer isn't in the sources, say plainly that you couldn't find it in the "
    "saved material — do NOT use outside knowledge or guess. Keep it concise."
)


class KnowledgeBase:
    def __init__(self, cfg: Config, db: "Database", llm):
        self.cfg = cfg
        self.db = db
        self.llm = llm
        self.embedder = Embedder(cfg)

    # --- indexing -----------------------------------------------------------
    def reindex(self) -> str:
        """Rebuild the whole index from notes, memories, and vault Markdown."""
        if not self.embedder.available:
            return self.embedder.setup_help()

        items = list(self._gather())
        if not items:
            return ("Nothing to index yet. Add a note (/note ...), a memory "
                    "(/remember ...), or Markdown files to your vault, then /index.")

        self.db.clear_knowledge()
        indexed, failed = 0, 0
        for source, ref, text in items:
            for i, chunk in enumerate(chunk_text(text)):
                vec = self.embedder.embed(chunk)
                if vec is None:
                    failed += 1
                    continue
                self.db.add_knowledge(source, ref, i, chunk, json.dumps(vec))
                indexed += 1

        if indexed == 0:
            return ("Couldn't build the index — the embedding model didn't "
                    f"respond. Check `ollama pull {self.cfg.embed_model}` and that "
                    "Ollama is running.")
        msg = f"Indexed {indexed} passage(s) from {len(items)} source(s). Ask me with /ask."
        if failed:
            msg += f" ({failed} chunk(s) failed to embed — partial index.)"
        return msg

    def _gather(self):
        """Yield (source_label, ref, text) for everything indexable."""
        for r in self.db.list_notes(limit=10_000):
            yield ("note", f"note #{r['id']}", r["content"])
        for r in self.db.list_user_preferences():
            yield ("memory", r["key"], f"{r['key']}: {r['value']}")
        yield from self._gather_vault()
        yield from self._gather_docs()

    def _gather_docs(self):
        """Ingested documents (PDFs, text) copied into the docs folder by /doc."""
        docs = Path(self.cfg.docs_dir)
        if not docs.exists():
            return
        # extract_text handles PDF (via pypdf) and plain text; imported lazily
        # so a machine without pypdf can still index notes/vault.
        from app.tools.documents import extract_text
        count = 0
        for path in sorted(docs.rglob("*")):
            if count >= _MAX_VAULT_FILES or not path.is_file():
                continue
            if path.suffix.lower() not in (".pdf", ".txt", ".md", ".markdown"):
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                text = extract_text(path)
            except Exception as exc:
                log.warning("Skipping doc %s: %s", path.name, exc)
                continue
            if text and text.strip():
                count += 1
                yield ("document", path.name, text)

    def _gather_vault(self):
        vault = Path(self.cfg.obsidian_vault).expanduser()
        if not vault.exists():
            return
        count = 0
        for path in sorted(vault.rglob("*")):
            if count >= _MAX_VAULT_FILES:
                log.warning("Vault index cap (%d files) reached.", _MAX_VAULT_FILES)
                break
            if path.suffix.lower() not in (".md", ".markdown", ".txt"):
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if text.strip():
                count += 1
                yield ("vault", path.name, text)

    # --- retrieval ----------------------------------------------------------
    def search(self, query: str, k: int = _TOP_K) -> list[tuple[float, str, str, str]]:
        """Return [(score, source, ref, content)] for the top-k closest chunks."""
        qvec = self.embedder.embed(query)
        if qvec is None:
            return []
        scored = []
        for row in self.db.all_knowledge():
            try:
                vec = json.loads(row["embedding"])
            except (ValueError, TypeError):
                continue
            scored.append((cosine(qvec, vec), row["source"], row["ref"], row["content"]))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [s for s in scored[:k] if s[0] >= _MIN_SCORE]

    # --- ask ----------------------------------------------------------------
    def ask(self, question: str) -> str:
        question = question.strip()
        if not question:
            return "Ask me something about your notes, e.g. /ask what did I decide about the thesis topic?"
        if self.db.knowledge_count() == 0:
            if not self.embedder.available:
                return self.embedder.setup_help()
            return "Your knowledge index is empty. Run /index first (after adding notes or vault files)."
        if not self.embedder.available:
            return self.embedder.setup_help()

        hits = self.search(question)
        if not hits:
            return ("I couldn't find anything about that in your saved notes, "
                    "memories or vault. If you've added material recently, run "
                    "/index to refresh, then ask again.")

        blocks, refs = [], []
        for i, (_score, source, ref, content) in enumerate(hits, 1):
            label = f"{source}: {ref}" if ref else source
            blocks.append(f"[{i}] ({label})\n{content}")
            refs.append(f"  [{i}] {label}")
        context = RAG_INSTRUCTION + "\n\n--- SOURCES ---\n" + "\n\n".join(blocks)

        try:
            answer = self.llm.chat(question, context_block=context)
        except Exception as exc:
            log.exception("RAG answer failed")
            return f"Found relevant notes but couldn't compose an answer: {exc}"
        return f"{answer}\n\nSources:\n" + "\n".join(refs)
