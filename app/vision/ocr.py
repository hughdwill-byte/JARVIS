"""Local OCR via Tesseract — free, offline, good for clean printed text.

The vision LLM (image_analyzer.read_text) is better for messy photos and
handwriting; this local path costs nothing and works with no API key.
Requires the tesseract binary:
  Windows: installer from github.com/UB-Mannheim/tesseract
  macOS:   brew install tesseract
  Linux/Pi: sudo apt install tesseract-ocr
"""

from __future__ import annotations

from pathlib import Path

from app.logger import get_logger

log = get_logger("ocr")

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None


def ocr_available() -> bool:
    if pytesseract is None or Image is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def read_image_text(image_path: str | Path) -> str:
    if pytesseract is None or Image is None:
        return ("Local OCR needs: pip install pytesseract pillow — plus the tesseract "
                "binary (see app/vision/ocr.py header for per-OS install commands).")
    try:
        text = pytesseract.image_to_string(Image.open(image_path)).strip()
    except pytesseract.TesseractNotFoundError:
        return ("The tesseract binary isn't installed or isn't on PATH. "
                "macOS: brew install tesseract | Linux/Pi: sudo apt install tesseract-ocr | "
                "Windows: install from github.com/UB-Mannheim/tesseract.")
    except Exception as exc:
        log.error("OCR failed: %s", exc)
        return f"OCR failed: {exc}"
    return text if text else "I couldn't find readable text — try better lighting or moving the page closer."
