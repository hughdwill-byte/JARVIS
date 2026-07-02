"""Project folder awareness: scan a directory and let the LLM discuss it.

Safety: only reads inside PROJECTS_DIR from .env (or a path you pass
explicitly), skips hidden/vendor dirs, reads code files only, caps sizes.
"""

from __future__ import annotations

from pathlib import Path

from app.brain.llm_client import LLMClient
from app.config import Config

CODE_SUFFIXES = {".py", ".js", ".ts", ".html", ".css", ".c", ".cpp", ".h", ".java",
                 ".rs", ".go", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".sh"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
             ".idea", ".vscode", "data"}
MAX_FILE_CHARS = 6_000
MAX_TOTAL_CHARS = 30_000
MAX_FILES = 40


def scan_tree(root: Path) -> list[Path]:
    """Code/text files under root, skipping vendor dirs, smallest-first cap."""
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS or part.startswith(".") for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in CODE_SUFFIXES:
            found.append(path)
        if len(found) >= MAX_FILES:
            break
    return found


def build_digest(root: Path) -> str:
    """File tree + truncated contents, capped so the LLM call stays cheap."""
    files = scan_tree(root)
    if not files:
        return ""
    lines = [f"Project folder: {root}", "Files:"]
    lines += [f"  {f.relative_to(root)}" for f in files]
    total = 0
    for f in files:
        if total >= MAX_TOTAL_CHARS:
            lines.append("\n[...remaining files omitted to keep the request small...]")
            break
        try:
            content = f.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_CHARS]
        except OSError:
            continue
        total += len(content)
        lines.append(f"\n--- {f.relative_to(root)} ---\n{content}")
    return "\n".join(lines)


class ProjectTool:
    def __init__(self, cfg: Config, llm: LLMClient):
        self.cfg = cfg
        self.llm = llm
        self._digest = ""
        self._root: Path | None = None

    def load(self, path_str: str) -> str:
        path_str = path_str.strip().strip('"').strip("'")
        root = Path(path_str).expanduser() if path_str else self.cfg.projects_dir
        if root is None:
            return ("Give me a folder: /project ~/uni/comp2000-assignment "
                    "(or set PROJECTS_DIR in .env as the default).")
        if not root.is_dir():
            return f"Not a folder: {root}"
        self._digest = build_digest(root)
        self._root = root
        if not self._digest:
            return f"No readable code/text files found in {root}."
        n_files = self._digest.count("\n--- ")
        return (f"Loaded project '{root.name}' ({n_files} files digested). "
                "Ask me anything about it with /projq <question>.")

    def ask(self, question: str) -> str:
        if not self._digest:
            return "No project loaded. Use /project <folder> first."
        if not question.strip():
            return "Ask something, e.g. /projq why does main.py crash on empty input?"
        if not self.llm.available:
            return "Project Q&A needs an LLM key — add ANTHROPIC_API_KEY to .env."
        return self.llm.chat(
            f"You are helping with the user's own project. Here is a digest of it:\n\n"
            f"{self._digest}\n\nQuestion: {question}",
            force_smart=True,
        )
