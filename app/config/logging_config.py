from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.config.paths import LOGS_DIR


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure private local logs; document contents must never be logged."""
    logger = logging.getLogger("treetranslate")
    logger.setLevel(level)
    if any(getattr(handler, "_treetranslate_local", False) for handler in logger.handlers):
        return logger

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOGS_DIR / "treetranslate.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler._treetranslate_local = True
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
