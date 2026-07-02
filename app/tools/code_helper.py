"""Coding help: explain/debug/review pasted code, plus a SAFE sandboxed runner.

The sandbox runs Python in a subprocess with a timeout and no shell — good for
checking small snippets, not a general execution environment.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from app.brain.llm_client import LLMClient

RUN_TIMEOUT_SECONDS = 10
MAX_OUTPUT_CHARS = 4_000


class CodeHelper:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def assist(self, request: str) -> str:
        """/code <question + pasted code> -> debugging/review/explanation."""
        if not request.strip():
            return ("Paste code and a question: /code why does this loop never end? "
                    "<paste code>")
        if not self.llm.available:
            return "Code help needs the LLM — add ANTHROPIC_API_KEY to .env."
        return self.llm.chat(
            "Help with this coding question. If debugging: identify the bug, explain WHY "
            "it happens, then show the minimal fix. If reviewing: top 3 issues only. "
            f"Teach, don't just patch.\n\n{request}",
            force_smart=True,
        )

    @staticmethod
    def run_python(code: str) -> str:
        """/run <python code> -> execute in a subprocess sandbox and return output."""
        if not code.strip():
            return "Give me code to run: /run print(sum(range(10)))"
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "snippet.py"
            script.write_text(code, encoding="utf-8")
            try:
                proc = subprocess.run(
                    [sys.executable, "-I", str(script)],  # -I: isolated mode
                    capture_output=True, text=True,
                    timeout=RUN_TIMEOUT_SECONDS, cwd=tmp,
                )
            except subprocess.TimeoutExpired:
                return f"Timed out after {RUN_TIMEOUT_SECONDS}s — infinite loop, perhaps?"
            except OSError as exc:
                return f"Couldn't start Python subprocess: {exc}"
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        out = out.strip()[:MAX_OUTPUT_CHARS]
        status = "OK" if proc.returncode == 0 else f"exit code {proc.returncode}"
        return f"[{status}]\n{out or '(no output)'}"
