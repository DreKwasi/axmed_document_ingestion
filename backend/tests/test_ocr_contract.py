import json

import pytest
from pydantic import ValidationError

from app.extraction.ocr_client import request_ocr
from app.extraction.ocr_contract import OcrResult


def test_ocr_contract_requires_page_level_evidence_and_provider_metadata():
    result = OcrResult.model_validate(
        {
            "schema_version": "1.0",
            "provider": "modal",
            "model": "paddleocr-3.5",
            "configuration_version": "axmed-ocr-v1",
            "duration_ms": 421,
            "pages": [
                {
                    "original_page_number": 1,
                    "width": 1600,
                    "height": 2200,
                    "dpi": 200,
                    "lines": [
                        {
                            "text": "Amoxicillin",
                            "confidence": 0.94,
                            "bounds": [[0, 0], [100, 0], [100, 20], [0, 20]],
                        }
                    ],
                }
            ],
        }
    )

    assert result.pages[0].original_page_number == 1
    assert result.pages[0].lines[0].confidence == 0.94


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": "1.0", "pages": []},
        {
            "schema_version": "1.0",
            "provider": "modal",
            "model": "paddleocr",
            "configuration_version": "v1",
            "duration_ms": 1,
            "pages": [
                {
                    "original_page_number": 1,
                    "width": 1,
                    "height": 1,
                    "dpi": 1,
                    "lines": [{"text": "x", "confidence": 1, "bounds": [[0, 0]]}],
                }
            ],
        },
    ],
)
def test_ocr_contract_rejects_incomplete_or_unusable_provider_responses(payload):
    with pytest.raises(ValidationError):
        OcrResult.model_validate(payload)


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(
            {
                "schema_version": "1.0",
                "provider": "modal",
                "model": "paddleocr",
                "configuration_version": "v1",
                "duration_ms": 1,
                "pages": [],
            }
        ).encode()


def test_ocr_client_sends_bounded_authenticated_versioned_request(monkeypatch):
    submitted = []

    def fake_urlopen(request, timeout):
        submitted.append((request, timeout))
        return _Response()

    monkeypatch.setattr("app.extraction.ocr_client.urlopen", fake_urlopen)
    result = request_ocr(
        "https://ocr.example/v1/ocr",
        data=b"png-data",
        media_type="image/png",
        selected_original_pages=(1,),
        idempotency_key="job-1",
        deadline_ms=30_000,
        token="secret",
    )

    assert result.provider == "modal"
    request, timeout = submitted[0]
    assert timeout == 30
    assert request.get_header("Authorization") == "Bearer secret"
    assert b'"selected_original_pages": [1]' in request.data
