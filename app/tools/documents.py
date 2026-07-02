"""Document ingestion: PDFs and text files -> extracted text -> LLM summary.

Usage from the assistant:
  /doc <path>       ingest and summarise a document
  /docq <question>  ask about the most recently ingested document
"""

from __future__ import annotations

from pathlib import Path

from app.brain.llm_client import LLMClient
from app.config import Config
from app.logger import get_logger

log = get_logger("documents")

MAX_CHARS_TO_LLM = 24_000  # ~6k tokens; keeps summaries cheap
TEXT_SUFFIXES = {".txt", ".md", ".py", ".tex", ".csv", ".rst"}


def extract_text(path: str | Path) -> str:
    """Extract text from a PDF or plain-text file. Raises ValueError with a fix hint."""
    path = Path(path).expanduser()
    if not path.exists():
        raise ValueError(f"File not found: {path}. Check the path (use quotes if it has spaces).")
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError("PDF support needs: pip install pypdf")
        try:
            reader = PdfReader(str(path))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:
            raise ValueError(f"Could not read PDF: {exc}")
        if not text.strip():
            raise ValueError(
                "This PDF has no extractable text (probably a scanned image). "
                "Try photographing the page and using /read instead."
            )
        return text
    if path.suffix.lower() in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError(
        f"Unsupported file type '{path.suffix}'. I can read: .pdf, "
        + ", ".join(sorted(TEXT_SUFFIXES))
    )


class DocumentTool:
    def __init__(self, cfg: Config, llm: LLMClient):
        self.cfg = cfg
        self.llm = llm
        self._last_text: str = ""
        self._last_name: str = ""

    def ingest_and_summarise(self, path_str: str) -> str:
        path_str = path_str.strip().strip('"').strip("'")
        if not path_str:
            return "Give me a file path: /doc ~/Downloads/lecture4.pdf"
        try:
            text = extract_text(path_str)
        except ValueError as exc:
            return str(exc)

        self._last_text = text[:MAX_CHARS_TO_LLM]
        self._last_name = Path(path_str).name
        truncated = " (truncated for length)" if len(text) > MAX_CHARS_TO_LLM else ""

        if not self.llm.available:
            return (f"Loaded {self._last_name} ({len(text):,} chars{truncated}). "
                    "I can't summarise without an API key, but the text is loaded — "
                    "add ANTHROPIC_API_KEY to .env to enable summaries.")

        summary = self.llm.chat(
            f"Summarise this document for a university student. Give: 1) a 3-sentence "
            f"overview, 2) the key points as bullets, 3) any action items or deadlines "
            f"mentioned.\n\nDocument '{self._last_name}'{truncated}:\n\n{self._last_text}",
            force_smart=True,
        )
        return f"Summary of {self._last_name}:\n{summary}\n\n(Ask follow-ups with /docq <question>)"

    def ask(self, question: str) -> str:
        if not self._last_text:
            return "No document loaded yet. Use /doc <path> first."
        if not question.strip():
            return "Ask something, e.g. /docq what are the assessment deadlines?"
        return self.llm.chat(
            f"Answer using this document ('{self._last_name}'). Quote it where useful; "
            f"say if the answer isn't in it.\n\nDocument:\n{self._last_text}\n\n"
            f"Question: {question}",
            force_smart=True,
        )
