"""Shared, structured resolver boundary for semantic document extraction."""

import json
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.domain.contracts import CanonicalQuotation


def provider_name(url: str) -> str:
    return urlparse(url).netloc or "configured-resolver"


def request_canonical_quotation(
    url: str,
    *,
    operation: str,
    prompt_version: str,
    context: dict[str, Any],
    token: str | None,
) -> CanonicalQuotation:
    request_body = json.dumps(
        {
            "operation": operation,
            "prompt_version": prompt_version,
            "context": context,
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=request_body, headers=headers, method="POST")
    with urlopen(request, timeout=30) as response:  # noqa: S310 - operator-configured resolver URL.
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("quotation"), dict):
        raise ValueError("Resolver response must contain a quotation object.")
    return CanonicalQuotation.model_validate(payload["quotation"])
