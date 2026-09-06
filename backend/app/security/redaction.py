"""Small deterministic privacy boundary for worker inputs and observability."""

import re
from typing import Any

EMAIL_PATTERN = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{6,}\d)(?!\w)")


def redact_text(value: str) -> str:
    """Remove contact identifiers while preserving structure useful to a resolver."""

    return PHONE_PATTERN.sub("[redacted-phone]", EMAIL_PATTERN.sub("[redacted-email]", value))


def redact_for_model(value: Any) -> Any:
    """Recursively redact untrusted values before a model or event sees them."""

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_for_model(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_for_model(item) for key, item in value.items()}
    return value
