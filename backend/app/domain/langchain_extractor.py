"""LangChain and Gemini (gemini-3.1-flash-lite) semantic extraction and reasoning engine.

Provides structured Pydantic extraction across email threads, native PDFs, OCR scans,
and progressive novel JSON schema mapping per PRD Sections 5, 31, 42, and 43.
"""

import json
import time
from decimal import Decimal
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.domain.contracts import CanonicalQuotation
from app.domain.schema_mapping import MappingProposal

CANONICAL_QUOTATION_PROMPT_VERSION = "canonical-quotation-v4"


class ProposedMappingSchema(BaseModel):
    required_fields: dict[str, str] = Field(default_factory=dict)
    quotation: dict[str, str | None] = Field(default_factory=dict)
    supplier: dict[str, str | None] = Field(default_factory=dict)
    commercial_terms: dict[str, str | None] = Field(default_factory=dict)
    line_items: dict[str, Any] = Field(default_factory=dict)


class LangChainSemanticExtractor:
    """Structured semantic extraction engine powered by LangChain and Google Gemini."""

    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-lite"):
        self.api_key = api_key
        self.model_name = model or "gemini-3.1-flash-lite"
        self._llm = ChatGoogleGenerativeAI(
            model=self.model_name,
            google_api_key=self.api_key,
            temperature=0.0,
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
            "3. Commercial Terms: Extract currency, incoterms, payment terms, MOQ, lead times, and pack pricing. "
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
            "For PDF input, `liteparse` is the source representation. Preserve its page and reading-order context; "
            "do not infer a value from a neighboring row or calculate a replacement for a value that is present. "
            "If a row/column relationship is not reliable, leave the affected field null and add a review issue.\n"
            "For pharmaceutical tables, map the INN/active-moiety column to product.inn and pair each strength with "
            "its ingredient. Preserve combination ingredient qualifiers exactly in product.inn, including any "
            "parenthetical salt/source phrase such as `Clavulanic acid (as potassium clavulanate)`, but use the "
            "base active "
            "moiety name for the corresponding strength. Keep packaging.primary_pack as "
            "the complete named container/material phrase (for example `PVC/Alu blister`), while packaging.description "
            "retains the full pack text and packaging.presentation contains only the form qualifier.\n"
            "Use the supplier header for supplier country and the complete named place, including any code "
            "in parentheses, "
            "for incoterms. Derive dosage_form from the pharmaceutical form phrase, never from a container or UOM; "
            "for example, `Pressurised inhalation suspension` has dosage_form `suspension`.\n"
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

    def propose_schema_mapping(
        self,
        unmapped_payload: dict[str, Any],
        schema_fingerprint: str,
        *,
        source_system: str = "unknown",
    ) -> MappingProposal:
        """Analyze unfamiliar supplier schema paths and propose a canonical mapping per PRD §31."""
        started_at = time.perf_counter()

        system_prompt = (
            "You are a schema mapping intelligence specialist for pharmaceutical procurement.\n"
            "Analyze the given raw supplier JSON payload structure and keys, and map the source dot-notation paths "
            "to Axmed canonical fields (quotation_reference, rfq_reference, issue_date, valid_until, supplier name, "
            "currency, incoterms, line items collection_path, trade_name, inn, quoted_price_amount, "
            "quoted_price_uom, pack_price, moq, units_per_pack). For every price source, map its amount and "
            "its source-specific basis separately. Do not use a generic `pack` constant unless the source schema "
            "itself explicitly defines the price as per pack.\n"
            "Return a structured ProposedMappingSchema object."
        )

        sample_context = {
            "source_system": source_system,
            "schema_fingerprint": schema_fingerprint,
            "payload_sample": unmapped_payload,
        }

        structured_llm = self._llm.with_structured_output(ProposedMappingSchema, include_raw=True)
        mapping_prompt = f"Propose a canonical field mapping for this schema:\n\n{json.dumps(sample_context, indent=2)}"
        result = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=mapping_prompt),
            ]
        )

        mapping_result, usage = _structured_result(result, ProposedMappingSchema)
        duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
        return MappingProposal(
            mapping=mapping_result.model_dump(),
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            estimated_cost_usd=usage["estimated_cost_usd"],
            provider=f"google-gemini/{self.model_name}",
            duration_ms=duration_ms,
        )


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
