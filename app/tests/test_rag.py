"""Phase 3 RAG: embeddings helpers, knowledge store, and /ask /index wiring.

No Ollama server needed — the Embedder is stubbed so we test chunking, cosine,
retrieval ranking, citation formatting, and graceful degradation offline.
"""

from pathlib import Path

import pytest

from app.assistant import Assistant
from app.brain.embeddings import chunk_text, cosine
from app.brain.rag import KnowledgeBase
from app.config import Config


def _cfg(tmp_path, **kw):
    base = dict(
        llm_provider="none", vision_provider="none", stt_provider="none",
        tts_provider="none", database_path=tmp_path / "t.db",
        mcp_config_path=tmp_path / "m.json", obsidian_vault=tmp_path / "vault",
    )
    base.update(kw)
    return Config(**base)


# --- embedding helpers --------------------------------------------------------

def test_cosine_basic():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([1, 1], [-1, -1]) == pytest.approx(-1.0)
    assert cosine([], [1]) == 0.0
    assert cosine([0, 0], [1, 1]) == 0.0  # zero vector -> 0, no divide error


def test_chunk_text_short_and_long():
    assert chunk_text("") == []
    assert chunk_text("just a short note") == ["just a short note"]
    big = "\n\n".join(f"Paragraph {i} with some words in it." for i in range(60))
    chunks = chunk_text(big, size=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 260 for c in chunks)  # size + a little slack
    # overlap means consecutive chunks share a tail/head — index stays covered
    assert "Paragraph 0" in chunks[0]


# --- a fake embedder: deterministic vectors from word overlap -----------------

class _FakeEmbedder:
    """Bag-of-words vector over a tiny fixed vocab — deterministic, offline."""
    available = True
    _vocab = ["thermo", "thesis", "cat", "resistor", "budget", "exam", "coffee"]

    def embed(self, text):
        t = text.lower()
        v = [float(t.count(w)) for w in self._vocab]
        return v if any(v) else [0.01] * len(self._vocab)  # avoid all-zero

    def setup_help(self):
        return "SETUP_HELP"


def _kb(tmp_path, llm=None):
    cfg = _cfg(tmp_path)
    from app.memory.database import Database
    db = Database(cfg.database_path)
    kb = KnowledgeBase(cfg, db, llm or _StubLLM())
    kb.embedder = _FakeEmbedder()
    return kb, db


class _StubLLM:
    """Echoes the RAG context so tests can assert what the model was given."""
    last_context = None

    def chat(self, question, context_block="", **kw):
        _StubLLM.last_context = context_block
        return "Answer drawn from [1]."


# --- indexing + retrieval -----------------------------------------------------

def test_reindex_counts_notes_memories_and_vault(tmp_path):
    kb, db = _kb(tmp_path)
    db.add_note("the thermo exam covers entropy")
    db.set_preference("coffee", "flat white")
    vault = Path(kb.cfg.obsidian_vault) / "JARVIS"
    vault.mkdir(parents=True)
    (vault / "thesis.md").write_text("my thesis is about resistor networks")
    msg = kb.reindex()
    assert "Indexed" in msg
    assert db.knowledge_count() >= 3  # note + memory + vault file


def test_reindex_empty_is_friendly(tmp_path):
    kb, _db = _kb(tmp_path)
    assert "Nothing to index" in kb.reindex()


def test_search_ranks_by_similarity(tmp_path):
    kb, db = _kb(tmp_path)
    db.add_note("thermo entropy and exam revision")
    db.add_note("my cat is called mittens")
    db.add_note("budget spreadsheet for the resistor order")
    kb.reindex()
    hits = kb.search("thermo exam")
    assert hits, "expected at least one hit"
    assert "thermo" in hits[0][3].lower()  # top hit is the thermo note


def test_ask_builds_cited_context_and_answers(tmp_path):
    kb, db = _kb(tmp_path)
    db.add_note("the thesis deadline is week 11")
    kb.reindex()
    out = kb.ask("when is the thesis due")
    assert "Answer drawn from [1]" in out
    assert "Sources:" in out and "[1]" in out
    # the model was handed cited source blocks + the no-guessing instruction
    assert "ONLY the numbered sources" in _StubLLM.last_context
    assert "[1] (note:" in _StubLLM.last_context


def test_ask_without_index_prompts_to_index(tmp_path):
    kb, _db = _kb(tmp_path)
    assert "index is empty" in kb.ask("anything").lower()


def test_ask_offline_embedder_gives_setup_help(tmp_path):
    kb, db = _kb(tmp_path)
    db.add_note("something")
    kb.reindex()
    kb.embedder.available = False  # Ollama went away
    assert kb.ask("something") == "SETUP_HELP"


def test_reindex_offline_embedder_gives_setup_help(tmp_path):
    kb, _db = _kb(tmp_path)
    kb.embedder.available = False
    assert kb.reindex() == "SETUP_HELP"


# --- assistant wiring ---------------------------------------------------------

def test_ask_index_commands_registered_and_offline_safe(tmp_path):
    bot = Assistant(_cfg(tmp_path))
    try:
        help_text = bot.handle("/help").text
        assert "/ask" in help_text and "/index" in help_text
        # offline (no Ollama): both must degrade gracefully, never crash
        idx = bot.handle("/index").text
        assert "Ollama" in idx or "Nothing to index" in idx
        ask = bot.handle("/ask what did I decide?").text
        assert isinstance(ask, str) and ask
    finally:
        bot.close()


def test_search_my_notes_phrase_routes_to_ask(tmp_path):
    bot = Assistant(_cfg(tmp_path))
    try:
        cmd, args = bot.router.route("search my notes about thermodynamics")
        assert cmd == "ask"
        assert args == "about thermodynamics"
    finally:
        bot.close()
