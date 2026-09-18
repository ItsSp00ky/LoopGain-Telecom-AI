"""Structured logging setup."""

from __future__ import annotations

import logging

from cvm.config import settings


def setup(name: str = "cvm") -> logging.Logger:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    )
    return logging.getLogger(name)