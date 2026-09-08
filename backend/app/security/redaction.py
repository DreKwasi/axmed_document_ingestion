"""Deterministic privacy boundary: redacts emails and phone numbers from inputs."""

import re
from typing import Any

# --- Section 1: Regex Pattern Matchers ---

EMAIL_PATTERN = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")

# Require explicit prefix/formatting so quotation refs (e.g. 2026-0812) are not masked.
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+\d[\d .()\-]{6,}\d|\d(?=[\d .()\-]{8,}\d)(?=[\d .()\-]*[ ()])[\d .()\-]{6,}\d)(?!\w)"
)

# --- Section 2: Redaction Functions ---


def redact_text(value: str) -> str:
    """Mask email addresses and telephone numbers in text."""
    return PHONE_PATTERN.sub("[redacted-phone]", EMAIL_PATTERN.sub("[redacted-email]", value))


def redact_for_model(value: Any) -> Any:
    """Recursively redact untrusted values before sending to LLM or event logs."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_for_model(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_for_model(item) for key, item in value.items()}
    return value

