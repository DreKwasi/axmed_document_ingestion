"""HTTP adapter for the Axmed-owned, versioned OCR service contract."""

import base64
import json
from urllib.request import Request, urlopen

from app.domain.ocr_contract import OcrResult


def request_ocr(
    url: str,
    *,
    data: bytes,
    media_type: str,
    selected_original_pages: tuple[int, ...],
    idempotency_key: str,
    deadline_ms: int,
    token: str | None,
) -> OcrResult:
    body = json.dumps(
        {
            "schema_version": "1.0",
            "media_type": media_type,
            "content_base64": base64.b64encode(data).decode("ascii"),
            "selected_original_pages": list(selected_original_pages),
            "idempotency_key": idempotency_key,
            "deadline_ms": deadline_ms,
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=max(1, deadline_ms // 1000)) as response:  # noqa: S310 - operator-configured service URL.
        return OcrResult.model_validate(json.loads(response.read().decode("utf-8")))
