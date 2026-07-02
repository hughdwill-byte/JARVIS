"""Image analysis: resize locally (cost control), then ask the vision LLM."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from app.brain.llm_client import LLMClient
from app.config import Config
from app.logger import get_logger
from app.prompts import DESK_ANALYSIS_PROMPT, OCR_ANALYSIS_PROMPT

log = get_logger("vision")

try:
    from PIL import Image
except ImportError:
    Image = None


def encode_image(path: str | Path, max_edge: int = 1024) -> tuple[str, str]:
    """Return (base64_jpeg, media_type), downscaled to cap API cost."""
    path = Path(path)
    if Image is not None:
        img = Image.open(path).convert("RGB")
        img.thumbnail((max_edge, max_edge))  # keeps aspect ratio, only shrinks
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"
    # Pillow missing — send the raw file (works, just costs more tokens).
    log.warning("Pillow not installed; sending full-size image. pip install pillow")
    data = path.read_bytes()
    media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return base64.standard_b64encode(data).decode(), media


class ImageAnalyzer:
    def __init__(self, cfg: Config, llm: LLMClient):
        self.cfg = cfg
        self.llm = llm

    @property
    def available(self) -> bool:
        return self.cfg.vision_provider != "none" and self.llm.available

    def _ask(self, image_path: str | Path, prompt: str) -> str:
        if not self.available:
            return (
                "Vision analysis needs the AI brain (Settings -> AI Brain). "
                f"The snapshot was still saved at {image_path} so nothing is lost."
            )
        # Claude Code / hybrid backends read the image file directly.
        file_fn = getattr(self.llm, "analyze_image_file", None)
        if file_fn is not None:
            return file_fn(str(image_path), prompt)
        b64, media = encode_image(image_path, self.cfg.vision_max_image_edge)
        return self.llm.analyze_image(b64, media, prompt)

    def describe_desk(self, image_path: str | Path) -> str:
        """Full desk description + OBJECTS: inventory line (see prompts.py)."""
        return self._ask(image_path, DESK_ANALYSIS_PROMPT)

    def read_text(self, image_path: str | Path) -> str:
        """Vision-LLM 'OCR' — reads pages, labels, whiteboards."""
        return self._ask(image_path, OCR_ANALYSIS_PROMPT)

    def ask_about(self, image_path: str | Path, question: str) -> str:
        """Free-form question about a snapshot ('where is my calculator?')."""
        return self._ask(
            image_path,
            f"Look at this desk snapshot and answer concisely, in a spoken style: {question}",
        )


def split_summary_and_objects(analysis: str) -> tuple[str, str]:
    """Split the model's reply into (summary, objects_csv) using the OBJECTS: line."""
    summary_lines: list[str] = []
    objects = ""
    for line in analysis.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("OBJECTS:"):
            objects = stripped[len("OBJECTS:"):].strip()
        elif stripped and not stripped.upper().startswith(("SUMMARY:", "1.", "2.")):
            summary_lines.append(stripped)
        elif stripped.upper().startswith("SUMMARY:"):
            summary_lines.append(stripped[len("SUMMARY:"):].strip())
    return " ".join(summary_lines).strip() or analysis.strip(), objects
