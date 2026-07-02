"""Document ingestion: text extraction and graceful failures."""

import pytest

from app.brain.llm_client import LLMClient
from app.tools.documents import DocumentTool, extract_text


def test_extract_text_from_txt(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("Lecture 4: dynamic programming basics.")
    assert "dynamic programming" in extract_text(f)


def test_extract_text_missing_file():
    with pytest.raises(ValueError, match="not found"):
        extract_text("/no/such/file.pdf")


def test_extract_text_unsupported_type(tmp_path):
    f = tmp_path / "image.xyz"
    f.write_text("data")
    with pytest.raises(ValueError, match="Unsupported"):
        extract_text(f)


def test_ingest_without_api_key(cfg, tmp_path):
    f = tmp_path / "reading.md"
    f.write_text("# Week 5\nGraph traversal, BFS vs DFS.")
    tool = DocumentTool(cfg, LLMClient(cfg))
    reply = tool.ingest_and_summarise(str(f))
    assert "reading.md" in reply
    assert "API key" in reply  # loaded but can't summarise — explains why
    assert "No document loaded" not in tool.ask("what topics?")


def test_docq_before_doc(cfg):
    tool = DocumentTool(cfg, LLMClient(cfg))
    assert "No document loaded" in tool.ask("anything?")
