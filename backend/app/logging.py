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
    """Return the dedicated API lifecycle logger used in every server mode.

    Uvicorn applies its logging configuration after importing the application.
    Configuring the root logger during import is therefore unreliable: application
    records can disappear even while Uvicorn's own records remain visible.  This
    logger owns a single stderr handler and does not propagate, so ingestion
    lifecycle records consistently reach the terminal in local and deployed runs.
    """

    # Silence redundant Google AFC warning from google-genai SDK
    try:
        from google.genai.models import Models

        Models._logged_afc_warning = True
    except Exception:
        pass

    logger = logging.getLogger("axmed.api")
    logger.setLevel(level)
    logger.disabled = False
    logger.propagate = False

    if not any(handler.get_name() == "axmed-lifecycle" for handler in logger.handlers):
        # Use the original process stderr rather than a framework-rebound stream.
        # This is the stream Uvicorn exposes in the developer terminal.
        handler = logging.StreamHandler(sys.__stderr__)
        handler.setFormatter(ColorFormatter())
        handler.setLevel(level)
        handler.set_name("axmed-lifecycle")
        logger.addHandler(handler)

    return logger
