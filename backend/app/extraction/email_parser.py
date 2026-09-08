"""Deterministic, non-rendering MIME parser for the email ingestion boundary."""

import re
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser

from app.security.redaction import redact_text

# --- Section 1: Regex Heuristics ---

GREETING_PATTERN = re.compile(r"(?im)^dear\s+[^\n,]+,\s*\n+")
SIGNATURE_PATTERN = re.compile(
    r"(?ims)^\s*(?:best regards|kind regards|regards|sincerely)[,\s]*\n"
    r"(?P<signature>.*?)(?=^\s*(?:p\.?s\.?\s*[:.-]|postscript\s*[:.-])|\Z)"
)
LEGAL_ENTITY_LINE_PATTERN = re.compile(
    r"(?i)^.*\b(?:inc\.?|incorporated|ltd\.?|limited|llc|plc|gmbh|ag|s\.p\.a\.?|s\.r\.l\.?|"
    r"sa|sas|bv|nv|oy|ab|pte\.?(?:\s+ltd\.?)?)\b.*$"
)

# --- Section 2: Data Transfer Objects ---


@dataclass(frozen=True)
class ParsedEmail:
    """Sanitized email payload ready for semantic LLM reasoning."""

    subject: str
    message_id: str | None
    body_text: str
    supplier_organization: str | None = None


# --- Section 3: MIME Traversal & Sanitization Pipeline ---


def _signature_organization(body_text: str) -> str | None:
    """Extract legal corporate organization from a sign-off while discarding personal names."""
    match = SIGNATURE_PATTERN.search(body_text)
    if not match:
        return None
    for line in match.group("signature").splitlines():
        candidate = line.strip()
        if "|" in candidate:
            candidate = candidate.rsplit("|", maxsplit=1)[-1].strip()
        if candidate and LEGAL_ENTITY_LINE_PATTERN.fullmatch(candidate):
            return redact_text(candidate)
    return None


def parse_email(data: bytes) -> ParsedEmail:
    """Parse raw RFC 822 email bytes into sanitized plaintext.

    Extracts `text/plain` parts, discards attachments/HTML execution, extracts
    corporate organization names, removes personal greetings/signatures, and applies
    contact PII redactions.

    Args:
        data: Raw binary email bytes.

    Returns:
        ParsedEmail instance containing cleaned body text and metadata.
    """
    message = BytesParser(policy=policy.default).parsebytes(data)
    plain_parts = [
        part.get_content()
        for part in message.walk()
        if part.get_content_type() == "text/plain" and not part.get_content_disposition() == "attachment"
    ]
    unique_parts = list(dict.fromkeys(part.strip() for part in plain_parts if isinstance(part, str) and part.strip()))
    body_text = "\n\n".join(unique_parts)
    supplier_organization = _signature_organization(body_text)
    body_text = GREETING_PATTERN.sub("", body_text)
    body_text = SIGNATURE_PATTERN.sub("", body_text)
    return ParsedEmail(
        subject=str(message.get("Subject", "")),
        message_id=message.get("Message-ID"),
        body_text=redact_text(body_text).strip(),
        supplier_organization=supplier_organization,
    )
