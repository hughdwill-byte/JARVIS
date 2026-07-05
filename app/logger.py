"""Logging setup: console + rotating file under data/logs/."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.config import Config

_configured = False


def setup_logging(cfg: Config) -> logging.Logger:
    global _configured
    root = logging.getLogger("jarvis")
    if _configured:
        return root

    root.setLevel(logging.DEBUG if cfg.debug else logging.INFO)

    # Redact secrets/emails from every log line before it's written anywhere.
    from app.brain.security import RedactionFilter
    redaction = RedactionFilter()

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if cfg.debug else logging.WARNING)
    console.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    console.addFilter(redaction)
    root.addHandler(console)

    try:
        cfg.ensure_dirs()
        file_handler = RotatingFileHandler(
            cfg.logs_dir / "assistant.log", maxBytes=1_000_000, backupCount=3
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        file_handler.addFilter(redaction)
        root.addHandler(file_handler)
    except OSError as exc:  # unwritable disk shouldn't kill the assistant
        root.warning("Could not open log file (%s); logging to console only.", exc)

    _configured = True
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"jarvis.{name}")
