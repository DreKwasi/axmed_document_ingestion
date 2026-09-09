"""Google Gemini setup for application-controlled semantic extraction."""

import logging
from decimal import Decimal
from typing import Any

from langchain.chat_models import init_chat_model

from app.config import Config
from app.extraction.semantic import (
    SemanticExtractionRequest,
    run_semantic_extraction,
)

logger = logging.getLogger("app.extraction.llm")

# --- Section 1: Prompt Version Constants & Intermediate Enrichment Models ---

CANONICAL_QUOTATION_PROMPT_VERSION = "semantic-orchestration-v1"
JSON_CANONICAL_FIELD_DICTIONARY = {
    "quotation_reference": "Supplier quotation, quote, offer, proposal, or proforma reference/ID/number.",
    "rfq_reference": "Buyer RFQ, enquiry, tender, requisition, or request reference/ID/number.",
    "document_type": "Document kind such as supplier quotation, offer, proforma invoice, or email offer.",
    "issue_date": "Issued, quotation, quote, offer, or document date.",
    "valid_until": "Expiry, valid-through, validity end, or offer expiration date.",
    "supplier.name": "Supplier/vendor legal or trading name; prefer the complete legal name.",
    "supplier.supplier_code": "Supplier/vendor/account code or identifier.",
    "supplier.country": "Supplier address or explicitly stated supplier country.",
    "supplier.manufacturing_site": "Explicit manufacturing facility or site.",
    "commercial_terms.currency": "Quotation, offer, pricing, or line-item currency.",
    "commercial_terms.incoterm": "Incoterm or delivery/trade term such as CIP, FOB, CIF, DDP, or EXW.",
    "commercial_terms.incoterm_named_place": "Named destination/place attached to the Incoterm.",
    "commercial_terms.incoterm_country": "Country of the named Incoterm place, only when explicit or unambiguous.",
    "commercial_terms.payment_terms": "Payment method, timing, credit terms, LC, or advance/payment conditions.",
    "commercial_terms.price_basis": "Document-level stated basis or conditions applying to prices.",
    "commercial_terms.transit_time_days": "Single stated shipping, delivery, or transit duration in days.",
    "commercial_terms.transit_time_min_days": "Minimum of an explicit transit/shipping duration range.",
    "commercial_terms.transit_time_max_days": "Maximum of an explicit transit/shipping duration range.",
    "commercial_terms.hs_codes": "Shipment/product HS, harmonized-system, tariff, or customs codes.",
    "line_items[].source_key": "Source row, line, item, SKU, or product identifier.",
    "line_items[].product.trade_name": "Trade, brand, proprietary, marketed, or product name.",
    "line_items[].product.inn": "INN, generic name, active ingredient, active moiety, API, or composition.",
    "line_items[].product.strength": (
        "Strength, potency, dose, concentration, or composition quantity. Parse scalar source strings into structured "
        "ingredient/value/unit/per-value/per-unit entries."
    ),
    "line_items[].product.dosage_form": (
        "Dosage, pharmaceutical, or dose form such as tablet or solution for injection."
    ),
    "line_items[].product.manufacturer": "Explicit product manufacturer or manufacturing organization.",
    "line_items[].product.country_of_origin": "Explicit product origin, made-in, or country of manufacture.",
    "line_items[].packaging.description": (
        "Complete pack description, pack details, package configuration, presentation text, or packing specification."
    ),
    "line_items[].packaging.presentation": (
        "Explicit presentation, or the complete pack description/configuration when that is the source's equivalent."
    ),
    "line_items[].packaging.primary_pack": "Immediate container/material such as blister, bottle, vial, or ampoule.",
    "line_items[].packaging.units_per_pack": "Units, tablets, capsules, vials, or ampoules in one pack/carton/box.",
    "line_items[].packaging.unit_label": "Unit contained in the pack or the unit-of-measure for pack contents.",
    "line_items[].packaging.packs_per_shipper": "Packs, cartons, or boxes in an outer shipper/case.",
    "line_items[].quantity.quoted_quantity": "Quoted, offered, requested, order, or line quantity.",
    "line_items[].quantity.quoted_quantity_uom": "Explicit basis/unit for the quoted quantity.",
    "line_items[].quantity.quantity_basis": "Text explaining the quoted quantity basis.",
    "line_items[].quantity.minimum_order_quantity": "MOQ, minimum order, or minimum purchase quantity.",
    "line_items[].quantity.minimum_order_quantity_uom": "Explicit MOQ unit, including keys such as MOQ packs/boxes.",
    "line_items[].pricing.currency": "Line-level currency when distinct or explicitly repeated.",
    "line_items[].pricing.quoted_price.amount": (
        "Quoted, unit, per-UOM, per-item, each, offer, or tender price amount; includes price_per_uom."
    ),
    "line_items[].pricing.quoted_price.uom": "Explicit commercial price basis/UOM; never invent pack as a fallback.",
    "line_items[].pricing.pack_price": "Price per pack, carton, box, kit, bottle, or other stated package.",
    "line_items[].pricing.discount": "Explicit discount percentage or amount as represented by the source.",
    "line_items[].pricing.extended_price": "Line total, extended value, amount, or net line value.",
    "line_items[].pricing.price_tiers": "Quantity breaks, volume tiers, or tiered prices with their bases.",
    "line_items[].pricing.adjustments": "Freight, surcharge, tariff, rebate, discount, or other price adjustment.",
    "line_items[].supply.lead_time_days": "Single manufacturing/availability lead time in days.",
    "line_items[].supply.lead_time_min_days": "Minimum of an explicit manufacturing lead-time range.",
    "line_items[].supply.lead_time_max_days": "Maximum of an explicit manufacturing lead-time range.",
    "line_items[].supply.shelf_life_months": "Shelf life, expiry period, or product life in months.",
    "line_items[].supply.minimum_remaining_shelf_life_percent": "Minimum remaining shelf life in percentage points.",
    "line_items[].supply.storage_conditions": "Storage temperature, humidity, light, freezing, or handling conditions.",
    "line_items[].supply.cold_chain_required": "Explicit refrigeration/cold-chain requirement or temperature evidence.",
    "line_items[].regulatory.who_prequalified": "WHO prequalification flag or status.",
    "line_items[].regulatory.who_pq_reference": "WHO prequalification reference/identifier.",
    "line_items[].regulatory.registered_markets": "Countries or markets where the product is registered/authorized.",
    "line_items[].regulatory.registration_reference": "Registration, authorization, dossier, or variation reference.",
    "line_items[].regulatory.regulatory_status": "Approval, registration, authorization, pending, or variation status.",
}


# --- Section 2: Telemetry Helpers ---
def _sum_optional_counts(*values: int | None) -> int | None:
    """Sum provider token counts while preserving an entirely unavailable measurement."""
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _sum_optional_decimals(*values: Decimal | None) -> Decimal | None:
    """Sum provider costs while preserving an entirely unavailable measurement."""
    present = [value for value in values if value is not None]
    return sum(present, start=Decimal("0")) if present else None


def aggregate_semantic_telemetry(result: Any) -> dict[str, Any]:
    """Combine semantic pipeline model-call telemetry for persistence."""

    calls = result.telemetry
    return {
        "provider": calls[0].get("provider", "google-gemini") if calls else "google-gemini",
        "model": calls[0].get("model") if calls else None,
        "prompt_version": CANONICAL_QUOTATION_PROMPT_VERSION,
        "duration_ms": sum(int(call.get("duration_ms") or 0) for call in calls),
        "input_tokens": _sum_optional_counts(*(call.get("input_tokens") for call in calls)),
        "output_tokens": _sum_optional_counts(*(call.get("output_tokens") for call in calls)),
        "estimated_cost_usd": _sum_optional_decimals(*(call.get("estimated_cost_usd") for call in calls)),
        "model_call_count": len(calls),
        "validation_count": result.validation_count,
        "unresolved_issue_count": len(result.unresolved_issues),
        "termination_reason": result.termination_reason,
    }


# --- Section 3: Semantic Extraction Orchestration Entry Point ---


def extract_semantics(
    settings: Config,
    context: dict[str, Any],
    *,
    source_type: str,
    source_media: bytes | None = None,
    source_media_type: str | None = None,
):
    """Extract one prepared source using the application's configured provider chain."""
    if not settings.gemini_api_key:
        raise ValueError("Google Gemini semantic extraction is not configured.")

    model = init_chat_model(
        f"google_genai:{settings.gemini_model}",
        api_key=settings.gemini_api_key,
        timeout=settings.gemini_request_timeout_seconds,
    )

    semantic_context = dict(context)
    if source_type == "json":
        semantic_context["canonical_field_dictionary"] = JSON_CANONICAL_FIELD_DICTIONARY
    request = SemanticExtractionRequest(
        source_type=source_type,
        context=semantic_context,
        source_media=source_media,
        source_media_type=source_media_type,
    )
    logger.info(
        "[Provider] Semantic pipeline configured provider=google-gemini model=%s source_type=%s",
        settings.gemini_model,
        source_type,
    )
    return run_semantic_extraction(
        model,
        request,
        provider_name="google-gemini",
    )
