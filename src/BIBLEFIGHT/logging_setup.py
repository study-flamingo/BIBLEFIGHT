from __future__ import annotations

import logging
from typing import Optional


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging with a sensible format.

    INFO: concise timestamps and levels
    DEBUG: adds module and line numbers for deeper introspection
    """
    # Avoid duplicate handlers if already configured
    root = logging.getLogger()
    if root.handlers:
        # still allow changing level dynamically
        root.setLevel(level.upper())
        for handler in root.handlers:
            handler.setLevel(level.upper())
        return

    log_level = level.upper()
    if log_level == "DEBUG":
        fmt = "%(asctime)s | %(levelname)s | %(name)s:%(lineno)d | %(message)s"
    else:
        fmt = "%(asctime)s | %(levelname)s | %(message)s"

    logging.basicConfig(
        level=log_level,
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def ensure_logging_configured(level: Optional[str] = None) -> None:
    """Idempotently set up logging if not already configured."""
    root = logging.getLogger()
    if not root.handlers:
        configure_logging(level or "INFO")
    elif level:
        root.setLevel(level.upper())
        for handler in root.handlers:
            handler.setLevel(level.upper())


