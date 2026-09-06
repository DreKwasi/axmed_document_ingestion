import json
from pathlib import Path

from app.schema_mapping import apply_mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_missing_required_source_value_stays_null_and_creates_a_review_issue():
    payload = json.loads((PROJECT_ROOT / "sample_documents/sanova_offer_export_2026-08-03.json").read_text())
    mapping = json.loads((PROJECT_ROOT / "evals/recorded_mappings/sanova_erp_2_4_1.json").read_text())["mapping"]
    payload["offer"]["products"][0]["commercials"].pop("price_per_pack")

    quotation = apply_mapping(payload, mapping, source_document="missing-price.json", method="deterministic_mapping")

    assert quotation.line_items[0].pricing.pack_price is None
    assert quotation.review_issues[0].field_path == "line_items[0].pricing.pack_price"
    assert quotation.review_issues[0].code == "missing_required_source_value"
