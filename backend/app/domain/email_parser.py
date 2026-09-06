"""Deterministic, non-rendering MIME parser for the email ingestion boundary."""

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser

from app.security.redaction import redact_text


@dataclass(frozen=True)
class ParsedEmail:
    subject: str
    message_id: str | None
    body_text: str


def parse_email(data: bytes) -> ParsedEmail:
    """Prefer plain text and never execute or render HTML from an uploaded email."""

    message = BytesParser(policy=policy.default).parsebytes(data)
    plain_parts = [
        part.get_content()
        for part in message.walk()
        if part.get_content_type() == "text/plain" and not part.get_content_disposition() == "attachment"
    ]
    unique_parts = list(dict.fromkeys(part.strip() for part in plain_parts if isinstance(part, str) and part.strip()))
    return ParsedEmail(
        subject=str(message.get("Subject", "")),
        message_id=message.get("Message-ID"),
        body_text=redact_text("\n\n".join(unique_parts)),
    )
