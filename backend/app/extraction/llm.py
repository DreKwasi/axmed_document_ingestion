"""LangChain and Gemini (gemini-3.1-flash-lite) semantic extraction and reasoning engine."""

import base64
import json
import time
from decimal import Decimal
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.extraction.contracts import CanonicalQuotation, Regulatory, Supply
from app.extraction.json import JsonSemanticExtraction, JsonSourceFact

# --- Section 1: Prompt Version Constants & Intermediate Enrichment Models ---

CANONICAL_QUOTATION_PROMPT_VERSION = "canonical-quotation-v8"
JSON_SEMANTIC_EXTRACTION_PROMPT_VERSION = "json-semantic-extraction-v2"


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


class SemanticLineItemEnrichment(BaseModel):
    """Narrative-only fields to merge into an already structured line item."""

    source_key: str
    supply: Supply = Field(default_factory=Supply)
    regulatory: Regulatory = Field(default_factory=Regulatory)


class SemanticEnrichment(BaseModel):
    """Collection of narrative line-item enrichments from footnotes and appendices."""

    line_items: list[SemanticLineItemEnrichment] = Field(default_factory=list)


class JsonFactAudit(BaseModel):
    """Source facts omitted by a primary JSON semantic extraction pass."""

    source_facts: list[JsonSourceFact] = Field(default_factory=list)


# --- Section 2: LangChain Semantic Extractor Core Engine ---


class LangChainSemanticExtractor:
    """Structured semantic extraction engine powered by LangChain and Google Gemini."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.1-flash-lite",
        request_timeout_seconds: int = 60,
    ):
        self.api_key = api_key
        self.model_name = model or "gemini-3.1-flash-lite"
        self._llm = ChatGoogleGenerativeAI(
            model=self.model_name,
            api_key=self.api_key,
            temperature=0.0,
            request_timeout=request_timeout_seconds,
            retries=0,
        )

    def extract_canonical_quotation(
        self,
        context: dict[str, Any],
        *,
        source_type: str = "email",
        source_media: bytes | None = None,
        source_media_type: str | None = None,
    ) -> tuple[CanonicalQuotation, dict[str, Any]]:
        """Extract a structured CanonicalQuotation from sanitized text or visual media context."""
        started_at = time.perf_counter()

        system_prompt = (
            "You are an expert pharmaceutical document intelligence extractor for Axmed.\n"
            "Your role is to extract structured quotation details into a CanonicalQuotation object "
            "adhering strictly to the schema.\n\n"
            "Rules to follow strictly:\n"
            "1. Discourse & Chronological Corrections (PRD §43): In email threads or notes, if a supplier "
            "states a price or detail and subsequently provides a correction, amendment, or P.S. note "
            "(e.g., quoting EUR 0.128 and later correcting to EUR 0.134), you MUST extract the final corrected "
            "value in the quotation pricing (e.g. 0.134), and you MUST record the supersession in the line item's "
            "evidence list with `supersedes_source_path` pointing to the prior quote.\n"
            "2. Pharmaceutical Entity Resolution: Separate product trade names from International Nonproprietary "
            "Names (INN / generic names). Extract active ingredient strength (value and unit), dosage form "
            "(e.g., tablet, syrup, capsule) and packaging configuration.\n"
            "3. Commercial Terms: Extract currency, incoterms, payment terms, MOQ, lead times, transit duration, "
            "pack pricing, and shipment-level HS customs codes. Store transit duration in "
            "commercial_terms.transit_time_days (or transit_time_min_days and transit_time_max_days if a range "
            "is stated). Store a shipping/schedule list of HS codes in commercial_terms.hs_codes. "
            "Do not place HS codes in line-item regulatory fields or infer/store ATC codes. "
            "Preserve a supplier's full legal name, including legal suffixes such as S.p.A. or Ltd.\n"
            "When `supplier_organization` is supplied in the sanitized context, use it verbatim as supplier.name.\n"
            "Dates must be emitted as ISO `YYYY-MM-DD` values when the source provides a date.\n"
            "4. Table fidelity: Transcribe every numeric table value exactly. Do not round, scale, derive, "
            "or replace a quoted unit price, pack price, quantity, discount, or extended amount. "
            "Preserve the source's stated price basis and UOM exactly (for example, `box` must not become `pack`). "
            "For a tabular quotation, identify the column headings before extracting a row. Values beneath Qty, UOM, "
            "Unit price, Pack price, Discount, Extended value, MOQ, and Lead time belong only to those corresponding "
            "fields. A comma is a thousands separator (for example, `6,000,000` is six million), not a reason to "
            "truncate or calculate a new value. Do not calculate a price from quantity, discount, extended value, or "
            "packaging when the table already states the price.\n"
            "For PDF input, the deterministic document plan and native reading-order text are "
            "the source representation. "
            "Preserve their page context; "
            "do not infer a value from a neighboring row or calculate a replacement for a value that is present. "
            "If a row/column relationship is not reliable, leave the affected field null and add a review issue.\n"
            "For pharmaceutical tables, map the INN/active-moiety column to product.inn and pair each strength with "
            "its ingredient. Preserve combination ingredient qualifiers exactly in product.inn, including any "
            "parenthetical salt/source phrase such as `Clavulanic acid (as potassium clavulanate)`, but use the "
            "base active "
            "moiety name for the corresponding strength. Keep packaging.primary_pack as "
            "the complete named container/material phrase (for example `PVC/Alu blister`), while packaging.description "
            "retains the full pack text and packaging.presentation contains only the form qualifier.\n"
            "For a supplier quotation, keep `quotation_reference` (the supplier's own quotation number) "
            "separate from `rfq_reference` (the buyer enquiry/request it answers). Search document metadata, "
            "header tables, body text, and correspondence for both rather than treating either as a fallback for "
            "the other. Extract supplier.country from an explicit supplier address/header. Set a line item's "
            "product.country_of_origin only when the source explicitly connects manufacture/origin to that country. "
            "When the source states that all items or products are manufactured at a named supplier facility and the "
            "supplier header or address identifies the country of that same facility, you MUST set every affected "
            "line item's product.country_of_origin to that country and cite both source locations in evidence. "
            "Evidence emitted by this extraction must use extraction_method `llm_extraction`, never `manual`; "
            "`manual`/`human_corrected` are reserved for a human reviewer action. Cite a useful source location "
            "(page plus table/row/section or quoted statement), not merely a canonical field or mapping path. "
            "Do not infer product origin from an address without an explicit manufacture/origin statement. "
            "Extract the named Incoterm place and its country separately in commercial_terms.incoterm_named_place "
            "and commercial_terms.incoterm_country when the document or a standard location code identifies it. "
            "A delivery place is commercial context, not proof "
            "of product origin. Use the supplier header for the complete named incoterm place, including any code "
            "in parentheses, "
            "for incoterms. Derive dosage_form from the pharmaceutical form phrase, never from a container or UOM; "
            "for example, `Pressurised inhalation suspension` has dosage_form `suspension`.\n"
            "Semantic enrichment: After respecting the structured-table facts, read the full document's narrative, "
            "notes, footnotes, appendices, and shipping/regulatory sections. These sections can set values for a "
            "specific item, an item range/list, an exception, or all other items. Apply their explicit scope to the "
            "affected line items. Extract every stated supply field, including shelf_life_months, "
            "minimum_remaining_shelf_life_percent, lead_time_days, lead_time_min_days, lead_time_max_days, "
            "storage_conditions, and cold_chain_required; "
            "also extract stated MOQ, regulatory registration/reference/status, and registered markets. Do not leave "
            "one of those fields null merely because it appears outside the price table. Extract any stated shipment "
            "transit duration or shipping time into commercial_terms.transit_time_days (or transit_time_min_days and "
            "transit_time_max_days if a range is given). Do not treat transit, shipping, or delivery duration as "
            "product manufacturer lead time unless the source explicitly identifies it as lead time. Preserve an "
            "explicit lead-time range in lead_time_min_days and "
            "lead_time_max_days rather than collapsing it to one number; apply a document-wide shipping term to every "
            "applicable line item. Store a source percentage in percentage points "
            "(for example, 80 percent as 80, not 0.80). When a note supplies a registration or variation identifier, "
            "store it in registration_reference as well as its stated status.\n"
            "When packaging text says `20 tablets per pack`, `30 tablets per pack`, or `500 tablets per pack`, "
            "extract units_per_pack as the number and unit_label as the named unit; do the same for `25 ampoules "
            "per box`. A container-only phrase such as `60 mL bottle` has unit_label `bottle` and no units_per_pack. "
            "For strengths written as `X mg/5 mL`, set strength.per_value to 5 and strength.per_unit to `mL`.\n"
            "Never use `pack` as a fallback UOM. A pack, carton, kit, vial, bottle, box, or supplier term can "
            "have a different commercial basis; leave an absent basis null and retain the packaging facts needed "
            "for a reviewer to assess it.\n"
            "Preserve all line items in source order.\n"
            "5. Canonical normalization: Emit document_type as lowercase snake_case. Preserve the complete "
            "pharmaceutical dosage-form phrase, such as `film-coated tablet`, `chewable tablet`, or "
            "`solution for injection`. Do not split a dosage form into route or packaging presentation. Use the "
            "table's pack description as primary_pack and retain its stated unit label.\n"
            "6. Provenance: For every extracted value, emit an Evidence entry at the quotation or line-item level.\n"
            "Include the canonical field, extraction method, confidence based on observed source quality, "
            "and a source location "
            "such as `page 1` or `email body`. Do not claim a page or confidence that the context cannot support.\n"
            "7. Accuracy: Do NOT invent or hallucinate data. If a field is not present or unknown, leave it as null.\n"
        )
        if source_type == "ocr":
            system_prompt += (
                "For OCR-assisted sources, use the supplied OCR page text as transcription aid only. OCR text may "
                "be incomplete or out of sequence. Interpret it semantically; do not assume transcription line "
                "order defines table rows or field relationships.\n"
            )
        if source_type == "image_vision":
            system_prompt += (
                "For direct image vision, the attached original image is authoritative. Read the visual document "
                "semantically and recover its quotation fields directly; do not rely on an inferred OCR row map.\n"
            )

        user_content = json.dumps(
            {
                "source_type": source_type,
                "context": context,
            },
            indent=2,
        )

        structured_llm = self._llm.with_structured_output(CanonicalQuotation, include_raw=True)
        user_prompt = f"Please extract the canonical quotation from the following context:\n\n{user_content}"
        human_content: str | list[str | dict[Any, Any]] = user_prompt
        if source_media is not None:
            if source_media_type is None:
                raise ValueError("source_media_type is required when source_media is provided")
            human_content = [
                {"type": "text", "text": user_prompt},
                {
                    "type": "image" if source_media_type.startswith("image/") else "file",
                    "base64": base64.b64encode(source_media).decode("ascii"),
                    "mime_type": source_media_type,
                },
            ]
        result = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_content),
            ]
        )

        quotation, usage = _structured_result(result, CanonicalQuotation)
        # Re-validate provider-created model instances so the canonical contract's
        # normalization validators also apply when the provider bypasses construction hooks.
        quotation = CanonicalQuotation.model_validate(quotation.model_dump(mode="python"))
        duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
        telemetry = {
            "provider": "google-gemini",
            "model": self.model_name,
            "prompt_version": CANONICAL_QUOTATION_PROMPT_VERSION,
            "source_type": source_type,
            "duration_ms": duration_ms,
            **usage,
        }
        return quotation, telemetry

    def enrich_line_items_from_semantic_sections(
        self,
        context: dict[str, Any],
        quotation: CanonicalQuotation,
    ) -> tuple[SemanticEnrichment, dict[str, Any]]:
        """Recover narrative supply/regulatory facts without re-sending table layout."""
        started_at = time.perf_counter()
        semantic_pages = context.get("semantic_pages") or context.get("pages", [])
        source_lines = [
            {"source_key": line.source_key, "trade_name": line.product.trade_name}
            for line in quotation.line_items
            if line.source_key
        ]
        system_prompt = (
            "You enrich an existing pharmaceutical quotation from narrative-only source sections. "
            "Do not change product identity, table quantities, prices, packaging, or commercial terms. "
            "Return only explicitly stated supply and regulatory values for the supplied source_key values. "
            "Apply notes scoped to a particular item, a list/range, an exception, or all remaining items. "
            "Extract shelf life, minimum remaining shelf life, storage, cold chain, lead time, registration status, "
            "registration/variation references, and registered markets. A percentage is expressed in percentage points "
            "(80 percent is 80). Do not infer facts not stated in the narrative."
        )
        user_content = json.dumps(
            {
                "line_items": source_lines,
                "semantic_pages": semantic_pages,
            },
            indent=2,
        )
        structured_llm = self._llm.with_structured_output(SemanticEnrichment, include_raw=True)
        result = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Enrich these line items from the semantic sections:\n\n{user_content}"),
            ]
        )
        enrichment, usage = _structured_result(result, SemanticEnrichment)
        duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
        return enrichment, {
            "provider": "google-gemini",
            "model": self.model_name,
            "prompt_version": f"{CANONICAL_QUOTATION_PROMPT_VERSION}-semantic-enrichment",
            "duration_ms": duration_ms,
            **usage,
        }

    def extract_json_quotation(
        self,
        payload: dict[str, Any],
        profile: dict[str, Any],
        *,
        source_document: str,
        invalid_source_paths: list[str],
    ) -> tuple[JsonSemanticExtraction, dict[str, Any]]:
        """Extract a quotation from one arbitrary JSON document without schema reuse."""
        started_at = time.perf_counter()

        system_prompt = (
            "You extract supplier quotation facts from one JSON source document. This is not a schema-mapping task.\n"
            "Return a canonical quotation only where the source supports that interpretation, plus every "
            "quotation-relevant fact you recover. Each fact needs a JSONPath source_path.\n"
            "Use extraction_method `direct_json` only when fact.value exactly equals the scalar at source_path. "
            "Use `semantic_extraction` only for a clearly stated narrative interpretation; its source_path must point "
            "to the containing source text. Do not invent calculations or conversions.\n"
            "canonical_field is optional. If a fact cannot be confidently normalized into the canonical quotation, "
            "leave canonical_field null and keep it as an unmapped fact. That is a successful extraction and must not "
            "lower confidence. Do not emit a canonical value without a supporting source fact.\n"
            "The canonical quotation has a rigid schema, but the incoming JSON has no assumed structure. Do not infer "
            "a relationship merely because source keys look similar. Determine meaning from the key, value, sibling "
            "fields, parent object, and line-item context together. Source labels do not need to exactly equal "
            "canonical field names.\n\n"
            "Canonical field dictionary (descriptions include common source-language variants, not an exhaustive "
            f"allow-list):\n{json.dumps(JSON_CANONICAL_FIELD_DICTIONARY, indent=2, sort_keys=True)}\n\n"
            "Pharmaceutical and packaging normalization:\n"
            "- Pair combination strengths with INNs in source order when their counts and context align. For example, "
            "INN `Amoxicillin + Clavulanic acid` and strength `500 mg / 125 mg` become two strength entries.\n"
            "- Parse a single strength such as `1000 mg` into one entry. Parse `10 IU/mL` as value 10, unit IU, "
            "per_value 1, per_unit mL. Do not treat a slash as a concentration denominator when it separates the "
            "strengths of multiple ingredients.\n"
            "- A source `pack_description`, `pack details`, `packing`, or similarly labelled value can support "
            "packaging.description and packaging.presentation even when the word `presentation` is absent. Preserve "
            "the complete text in description/presentation, and also decompose explicit container and counts into "
            "primary_pack, units_per_pack, unit_label, and packs_per_shipper where supported.\n"
            "- A source `price_per_uom`, `unit price`, `price each`, or equivalent can support quoted_price.amount; "
            "use an explicit sibling UOM as quoted_price.uom and never invent the basis. A key such as "
            "minimum_order_quantity_packs explicitly supplies both the MOQ value and its `pack` UOM.\n\n"
            "Final completeness lookup: before returning, inspect every source leaf and every empty canonical field. "
            "Check whether an unused source fact or a partially interpreted composite value explicitly supports that "
            "field. Add every quotation-relevant source leaf to source_facts even when it remains unmapped. Fill only "
            "supported canonical fields, never overwrite a stronger value, and leave ambiguous destinations unmapped."
        )

        context = {
            "source_document": source_document,
            "structural_inventory": profile,
            "source_json": payload,
            "invalid_source_paths_from_previous_attempt": invalid_source_paths,
        }

        structured_llm = self._llm.with_structured_output(JsonSemanticExtraction, include_raw=True)
        result = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content=f"Extract quotation facts from this JSON document:\n\n{json.dumps(context, indent=2)}"
                ),
            ]
        )

        extraction, usage = _structured_result(result, JsonSemanticExtraction)

        audit_system_prompt = (
            "You audit one supplier quotation JSON extraction for omissions. Return only source facts omitted by the "
            "primary extraction. Each fact must use an exact JSONPath and its value must exactly equal the scalar or "
            "collection at that path. Use the canonical field dictionary to map a fact when its meaning is supported "
            "by its value and context; otherwise leave canonical_field null. A composite source value may be emitted "
            "more than once when it supports multiple populated canonical fields. Do not change the canonical "
            "quotation, calculate new commercial values, repeat already reported facts, or report invalid paths. "
            "The audit context lists every populated canonical field that still lacks a source fact. For each listed "
            "field, emit at least one supporting fact when the source supports it; otherwise leave it unsupported so "
            "the application can surface the provenance gap.\n\n"
            f"Canonical field dictionary:\n{json.dumps(JSON_CANONICAL_FIELD_DICTIONARY, indent=2, sort_keys=True)}"
        )
        audit_context = {
            "source_json": payload,
            "canonical_quotation": extraction.quotation.model_dump(mode="json"),
            "already_reported_source_paths": [fact.source_path for fact in extraction.source_facts],
            "populated_canonical_fields_without_source_fact": _populated_fields_without_source_fact(extraction),
            "invalid_source_paths": invalid_source_paths,
        }
        audit_llm = self._llm.with_structured_output(JsonFactAudit, include_raw=True)
        audit_result = audit_llm.invoke(
            [
                SystemMessage(content=audit_system_prompt),
                HumanMessage(
                    content=f"Audit this extraction for omitted facts:\n\n{json.dumps(audit_context, indent=2)}"
                ),
            ]
        )
        audit, audit_usage = _structured_result(audit_result, JsonFactAudit)
        known_facts = {
            (fact.source_path, fact.canonical_field, json.dumps(fact.value, default=str, sort_keys=True))
            for fact in extraction.source_facts
        }
        for fact in audit.source_facts:
            identity = (fact.source_path, fact.canonical_field, json.dumps(fact.value, default=str, sort_keys=True))
            if identity not in known_facts:
                extraction.source_facts.append(fact)
                known_facts.add(identity)

        duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
        return extraction, {
            "provider": "google-gemini",
            "model": self.model_name,
            "prompt_version": JSON_SEMANTIC_EXTRACTION_PROMPT_VERSION,
            "duration_ms": duration_ms,
            "input_tokens": _sum_optional_counts(usage["input_tokens"], audit_usage["input_tokens"]),
            "output_tokens": _sum_optional_counts(usage["output_tokens"], audit_usage["output_tokens"]),
            "estimated_cost_usd": _sum_optional_decimals(
                usage["estimated_cost_usd"], audit_usage["estimated_cost_usd"]
            ),
        }


# --- Section 3: Semantic Enrichment Merging Logic ---


def merge_semantic_enrichment(
    quotation: CanonicalQuotation,
    enrichment: SemanticEnrichment,
) -> CanonicalQuotation:
    """Fill omitted narrative facts without overwriting structured/table values."""
    enrichment_by_key = {item.source_key: item for item in enrichment.line_items}
    for line in quotation.line_items:
        if not line.source_key or line.source_key not in enrichment_by_key:
            continue
        source = enrichment_by_key[line.source_key]
        _fill_missing_model_values(line.supply, source.supply)
        _fill_missing_model_values(line.regulatory, source.regulatory)
    return quotation


def _fill_missing_model_values(target: Supply | Regulatory, source: Supply | Regulatory) -> None:
    """Copy non-empty values from source to target only where target currently has None or empty list."""
    for field_name in type(source).model_fields:
        source_value = getattr(source, field_name)
        target_value = getattr(target, field_name)
        if source_value is None or source_value == []:
            continue
        if target_value is None or target_value == []:
            setattr(target, field_name, source_value)


def _populated_fields_without_source_fact(extraction: JsonSemanticExtraction) -> list[str]:
    """List populated canonical fields that the primary JSON pass did not ground in a source fact."""
    payload = extraction.quotation.model_dump(mode="json")
    mapped_fields = {fact.canonical_field for fact in extraction.source_facts if fact.canonical_field}
    candidates: list[str] = []
    line_field_patterns = [field for field in JSON_CANONICAL_FIELD_DICTIONARY if "line_items[]" in field]
    document_field_patterns = [field for field in JSON_CANONICAL_FIELD_DICTIONARY if "line_items[]" not in field]
    for field_pattern in line_field_patterns:
        for index in range(len(payload.get("line_items", []))):
            candidates.append(field_pattern.replace("line_items[]", f"line_items[{index}]"))
    candidates.extend(document_field_patterns)

    return [
        field_path
        for field_path in candidates
        if field_path not in mapped_fields and _canonical_path_is_populated(payload, field_path)
    ]


def _canonical_path_is_populated(payload: dict[str, Any], field_path: str) -> bool:
    """Resolve one dictionary field path against a canonical quotation dump."""
    current: Any = payload
    for segment in field_path.split("."):
        if segment.startswith("line_items[") and segment.endswith("]"):
            index = int(segment.removeprefix("line_items[").removesuffix("]"))
            items = current.get("line_items") if isinstance(current, dict) else None
            if not isinstance(items, list) or index >= len(items):
                return False
            current = items[index]
            continue
        if not isinstance(current, dict) or segment not in current:
            return False
        current = current[segment]
    return current not in (None, "", [], {})


# --- Section 4: Token Usage & Structured Output Telemetry Parsers ---


def _structured_result(result: Any, expected_type: type[BaseModel]) -> tuple[Any, dict[str, Any]]:
    """Return parsed structured output and provider-reported usage without inventing token or cost data."""
    parsed = result
    raw = None
    if isinstance(result, dict) and "parsed" in result:
        parsed = result["parsed"]
        raw = result.get("raw")
    if not isinstance(parsed, expected_type):
        parsed = expected_type.model_validate(parsed)
    usage_metadata = getattr(raw, "usage_metadata", None) or {}
    response_metadata = getattr(raw, "response_metadata", None) or {}
    usage = usage_metadata or response_metadata.get("usage_metadata", {}) or response_metadata.get("usage", {})
    input_tokens = usage.get("input_tokens", usage.get("prompt_token_count"))
    output_tokens = usage.get("output_tokens", usage.get("candidates_token_count"))
    estimated_cost = usage.get("estimated_cost_usd")
    return parsed, {
        "input_tokens": _token_count(input_tokens),
        "output_tokens": _token_count(output_tokens),
        "estimated_cost_usd": Decimal(str(estimated_cost)) if estimated_cost is not None else None,
    }


def _token_count(value: Any) -> int | None:
    """Parse positive integer token count or return None."""
    if not isinstance(value, int | float | str):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _sum_optional_counts(*values: int | None) -> int | None:
    """Sum provider token counts while preserving an entirely unavailable measurement."""
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _sum_optional_decimals(*values: Decimal | None) -> Decimal | None:
    """Sum provider costs while preserving an entirely unavailable measurement."""
    present = [value for value in values if value is not None]
    return sum(present, start=Decimal("0")) if present else None
