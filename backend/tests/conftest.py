from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Config
from app.extraction.json import JsonExtractionProposal, JsonSemanticExtraction

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def disable_live_model_provider_credentials(monkeypatch: pytest.MonkeyPatch):
    """Keep the deterministic test suite offline despite developer shell credentials."""

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture
def sanova_json_extractor():
    """A test double for JSON API tests; production always invokes its provider."""

    quotation = JsonSemanticExtraction.model_validate(
        {
            "quotation": {
                "quotation_reference": "SNV/EXP/2026/0771",
                "supplier": {"name": "Sanova Laboratories Pvt. Ltd.", "country": "IN"},
                "commercial_terms": {
                    "currency": "EUR",
                    "incoterm": "FCA",
                    "payment_terms": "30% advance with PO, 70% against copy of Bill of Lading",
                },
                "line_items": [
                    {
                        "source_key": "SNV-TLD-90",
                        "product": {"trade_name": "Sanotri-TLD", "inn": ["Tenofovir", "Lamivudine", "Dolutegravir"]},
                        "packaging": {"units_per_pack": 90, "unit_label": "tablet"},
                        "quantity": {"minimum_order_quantity": "5000", "minimum_order_quantity_uom": "pack"},
                        "pricing": {
                            "currency": "EUR",
                            "pack_price": "3.15",
                            "quoted_price": {"amount": "3.15", "uom": "pack"},
                        },
                    },
                    {
                        "source_key": "SNV-RIF-HRZE",
                        "product": {"trade_name": "Sanofour Kit", "inn": ["Rifampicin"]},
                        "packaging": {"units_per_pack": 672, "unit_label": "tablet"},
                        "quantity": {"minimum_order_quantity": "2000", "minimum_order_quantity_uom": "pack"},
                        "pricing": {
                            "currency": "EUR",
                            "pack_price": "8.42",
                            "quoted_price": {"amount": "8.42", "uom": "pack"},
                        },
                    },
                    {
                        "source_key": "SNV-AMLO-5",
                        "product": {"trade_name": "Sanodip 5", "inn": ["Amlodipine besylate"]},
                        "packaging": {"units_per_pack": 30, "unit_label": "tablet"},
                        "quantity": {"minimum_order_quantity": "40000", "minimum_order_quantity_uom": "pack"},
                        "pricing": {
                            "currency": "EUR",
                            "pack_price": "0.312",
                            "quoted_price": {"amount": "0.312", "uom": "pack"},
                        },
                    },
                ],
            },
            "source_facts": [
                {
                    "label": "Quotation reference",
                    "value": "SNV/EXP/2026/0771",
                    "source_path": "$.offer.offer_reference",
                    "canonical_field": "quotation_reference",
                },
                {
                    "label": "Supplier",
                    "value": "Sanova Laboratories Pvt. Ltd.",
                    "source_path": "$.vendor.name",
                    "canonical_field": "supplier.name",
                },
                {
                    "label": "Pack price",
                    "value": 3.15,
                    "source_path": "$.offer.products[0].commercials.price_per_pack",
                    "canonical_field": "line_items[0].pricing.pack_price",
                },
            ],
        }
    )

    class Extractor:
        def extract(self, *_args, **_kwargs):
            return JsonExtractionProposal(
                extraction=quotation,
                provider="test-double",
                model="test",
                prompt_version="test",
                duration_ms=1,
            )

    return Extractor()


@pytest.fixture
def client(tmp_path: Path, sanova_json_extractor):
    settings = Config(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        golden_dataset_path=PROJECT_ROOT / "backend/evals/golden_dataset.json",
        background_processing_enabled=False,
    )
    with TestClient(create_app(settings, json_extractor=sanova_json_extractor)) as test_client:
        yield test_client


@pytest.fixture
def client_settings(tmp_path: Path):
    settings = Config(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        golden_dataset_path=PROJECT_ROOT / "backend/evals/golden_dataset.json",
        background_processing_enabled=False,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client, settings


@pytest.fixture
def sanova_bytes() -> bytes:
    return (PROJECT_ROOT / "backend/evals/fixtures/documents/sanova_offer_export_2026-08-03.json").read_bytes()
