from __future__ import annotations

import logging
import logging.config

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    level = "DEBUG" if settings.debug else "INFO"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "level": level,
                    "formatter": "standard",
                }
            },
            "root": {"level": level, "handlers": ["default"]},
            "loggers": {
                "uvicorn": {"level": level, "handlers": ["default"], "propagate": False},
                "uvicorn.access": {"level": level, "handlers": ["default"], "propagate": False},
                "oraculo_api": {"level": level, "handlers": ["default"], "propagate": False},
            },
        }
    )
