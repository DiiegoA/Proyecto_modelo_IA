from __future__ import annotations

import logging
import sys

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    root_level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(
        level=root_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
