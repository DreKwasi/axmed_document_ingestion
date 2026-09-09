"""Structured and readable console logging configuration for the Axmed API."""

import logging
import sys


class ColorFormatter(logging.Formatter):
    """Clean terminal formatter with distinct level badges."""

    GREY = "\x1b[38;20m"
    CYAN = "\x1b[36;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"

    FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s - %(message)s"

    LEVEL_COLORS = {
        logging.DEBUG: GREY,
        logging.INFO: CYAN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: BOLD_RED,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        formatter = logging.Formatter(
            f"{color}%(asctime)s{self.RESET} | {color}%(levelname)-7s{self.RESET} | %(name)s - %(message)s",
            datefmt="%H:%M:%S",
        )
        return formatter.format(record)


def get_api_logger(level: int = logging.INFO) -> logging.Logger:
    """Configure application console logging and return the API lifecycle logger.

    Uvicorn applies its logging configuration after importing the application.
    Configuring the root logger is therefore unreliable.  The application owns a
    single stderr handler on the ``app`` namespace instead: API, event, parser,
    and extraction child loggers all propagate to that handler without affecting
    Uvicorn's own logging configuration.
    """

    # Silence redundant Google AFC warning from google-genai SDK
    try:
        from google.genai.models import Models

        Models._logged_afc_warning = True
    except Exception:
        pass

    application_logger = logging.getLogger("app")
    application_logger.setLevel(level)
    application_logger.disabled = False
    application_logger.propagate = False

    # Uvicorn's dictConfig can leave already-imported child loggers disabled.
    # Re-enable the owned namespace explicitly so parser and event records are
    # not filtered before they reach the shared application handler.
    for candidate in logging.root.manager.loggerDict.values():
        if isinstance(candidate, logging.Logger) and candidate.name.startswith("app."):
            candidate.disabled = False

    if not any(handler.get_name() == "axmed-lifecycle" for handler in application_logger.handlers):
        # Use the active process stderr so local Uvicorn and platform log capture
        # receive the same records.
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(ColorFormatter())
        handler.setLevel(level)
        handler.set_name("axmed-lifecycle")
        application_logger.addHandler(handler)

    api_logger = logging.getLogger("app.api")
    api_logger.setLevel(level)
    api_logger.disabled = False
    return api_logger
