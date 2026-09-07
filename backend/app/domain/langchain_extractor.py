"""LangChain and Gemini (gemini-3.1-flash-lite) semantic extraction and reasoning engine.

Provides structured Pydantic extraction across email threads, native PDFs, OCR scans,
and per-document JSON semantic fact extraction.
"""

import json
import time
from decimal import Decimal
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.domain.contracts import CanonicalQuotation, Regulatory, Supply
from app.domain.json_extraction import JsonSemanticExtraction

CANONICAL_QUOTATION_PROMPT_VERSION = "canonical-quotation-v7"
JSON_SEMANTIC_EXTRACTION_PROMPT_VERSION = "json-semantic-extraction-v1"


class SemanticLineItemEnrichment(BaseModel):
    """Narrative-only fields to merge into an already structured line item."""

    source_key: str
    supply: Supply = Field(default_factory=Supply)
    regulatory: Regulatory = Field(default_factory=Regulatory)


class SemanticEnrichment(BaseModel):
    line_items: list[SemanticLineItemEnrichment] = Field(default_factory=list)


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
    ) -> tuple[CanonicalQuotation, dict[str, Any]]:
        """Extract a structured CanonicalQuotation from sanitized text context."""
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
            "3. Commercial Terms: Extract currency, incoterms, payment terms, MOQ, lead times, pack pricing, and "
            "shipment-level HS customs codes. Store a shipping/schedule list of HS codes in commercial_terms.hs_codes. "
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
            "one of those fields null merely because it appears outside the price table. Treat a stated transit or "
            "shipping time as delivery lead time. Preserve an explicit range in lead_time_min_days and "
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
            "5. Canonical normalization: Emit document_type as lowercase snake_case. Set dosage_form to the "
            "core pharmaceutical form only (for example `tablet`, not `film-coated tablet`). Put qualifiers "
            "such as `film-coated`, `chewable`, or `pressurised inhalation` in packaging.presentation. Use the "
            "table's pack description as primary_pack and retain its stated unit label.\n"
            "6. Provenance: For every extracted value, emit an Evidence entry at the quotation or line-item level.\n"
            "Include the canonical field, extraction method, confidence based on observed source quality, "
            "and a source location "
            "such as `page 1` or `email body`. Do not claim a page or confidence that the context cannot support.\n"
            "7. Accuracy: Do NOT invent or hallucinate data. If a field is not present or unknown, leave it as null.\n"
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
        result = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
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
            "a relationship merely because source keys look similar."
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
        duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
        return extraction, {
            "provider": "google-gemini",
            "model": self.model_name,
            "prompt_version": JSON_SEMANTIC_EXTRACTION_PROMPT_VERSION,
            "duration_ms": duration_ms,
            **usage,
        }


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
    for field_name in type(source).model_fields:
        source_value = getattr(source, field_name)
        target_value = getattr(target, field_name)
        if source_value is None or source_value == []:
            continue
        if target_value is None or target_value == []:
            setattr(target, field_name, source_value)


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
    if not isinstance(value, int | float | str):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
