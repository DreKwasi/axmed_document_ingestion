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
            "(e.g., tablet, vial, ampoule), and packaging configuration.\n"
            "3. Commercial Terms: Extract currency, incoterms, payment terms, MOQ, lead times, and pack pricing.\n"
            "4. Accuracy: Do NOT invent or hallucinate data. If a field is not present or unknown, leave it as null.\n"
        )

        user_content = json.dumps(
            {
                "source_type": source_type,
                "context": context,
            },
            indent=2,
        )

        structured_llm = self._llm.with_structured_output(CanonicalQuotation)
        user_prompt = f"Please extract the canonical quotation from the following context:\n\n{user_content}"
        quotation: CanonicalQuotation = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )

        duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
        telemetry = {
            "provider": "google-gemini",
            "model": self.model_name,
            "source_type": source_type,
            "duration_ms": duration_ms,
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
            "currency, incoterms, line items collection_path, trade_name, inn, pack_price, moq, units_per_pack).\n"
            "Return a structured ProposedMappingSchema object."
        )

        sample_context = {
            "source_system": source_system,
            "schema_fingerprint": schema_fingerprint,
            "payload_sample": unmapped_payload,
        }

        structured_llm = self._llm.with_structured_output(ProposedMappingSchema)
        mapping_prompt = f"Propose a canonical field mapping for this schema:\n\n{json.dumps(sample_context, indent=2)}"
        mapping_result: ProposedMappingSchema = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=mapping_prompt),
            ]
        )

        duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
        return MappingProposal(
            mapping=mapping_result.model_dump(),
            input_tokens=500,
            output_tokens=300,
            estimated_cost_usd=Decimal("0.0005"),
            provider=f"google-gemini/{self.model_name}",
            duration_ms=duration_ms,
        )
