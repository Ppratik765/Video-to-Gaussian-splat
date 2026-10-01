"""
Structured logging with per-stage log files and rich console output.

Responsibility: utils/logging.py
Milestone: M0
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_CONFIGURED = False


def setup_logging(
    *,
    level: int = logging.INFO,
    log_file: Path | None = None,
    rich_console: bool = True,
) -> logging.Logger:
    """Configure the ``splat360`` root logger.

    Parameters
    ----------
    level:
        Minimum log level.
    log_file:
        If given, also write to this file (append mode).
    rich_console:
        Use ``rich.logging.RichHandler`` if rich is installed.
        Falls back to a plain ``StreamHandler`` otherwise.

    Returns the root ``splat360`` logger.
    """
    global _CONFIGURED

    logger = logging.getLogger("splat360")
    logger.setLevel(level)

    if _CONFIGURED:
        return logger

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # Console handler
    console_handler: logging.Handler
    if rich_console:
        try:
            from rich.logging import RichHandler

            console_handler = RichHandler(
                level=level,
                show_path=False,
                markup=True,
                rich_tracebacks=True,
            )
        except ImportError:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    else:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    # Optional file handler
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        logger.addHandler(file_handler)

    _CONFIGURED = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``splat360`` namespace."""
    return logging.getLogger(f"splat360.{name}")
