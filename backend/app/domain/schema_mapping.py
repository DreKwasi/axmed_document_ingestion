import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from app.domain.contracts import (
    CanonicalQuotation,
    CommercialTerms,
    LineItem,
    Packaging,
    Pricing,
    Product,
    Quantity,
    QuotedPrice,
    Regulatory,
    ReviewIssue,
    Strength,
    Supplier,
    Supply,
    _core_dosage_form,
)


def normalize_key(value: str) -> str:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return "_".join(part for part in re.split(r"[^a-zA-Z0-9]+", separated.lower()) if part)


def normalized_paths(payload: Any, prefix: str = "") -> list[str]:
    if isinstance(payload, dict):
        paths: list[str] = []
        for key in sorted(payload):
            next_path = f"{prefix}.{normalize_key(key)}" if prefix else normalize_key(key)
            paths.extend(normalized_paths(payload[key], next_path))
        return paths or [prefix]
    if isinstance(payload, list):
        item_prefix = f"{prefix}[]"
        if not payload:
            return [item_prefix]
        paths = []
        for item in payload:
            paths.extend(normalized_paths(item, item_prefix))
        return sorted(set(paths))
    return [prefix]


def fingerprint(payload: Any) -> str:
    source = "\n".join(sorted(normalized_paths(payload)))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def get_path(payload: Any, path: str) -> Any:
    current = payload
    for segment in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


def scalar(item: dict[str, Any], path: str) -> Any:
    return get_path(item, path)


def resolve_mapping_value(item: dict[str, Any], specification: str | dict[str, str]) -> Any:
    if isinstance(specification, str):
        return scalar(item, specification)
    if "constant" in specification:
        return specification["constant"]
    source_value = scalar(item, specification["path"])
    if source_value is None:
        return None
    transform = specification.get("transform")
    if transform == "weeks_to_days":
        return int(source_value) * 7
    raise ValueError(f"Unsupported mapping transform: {transform}")


def as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


@dataclass(frozen=True)
class MappingProposal:
    mapping: dict[str, Any]
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: Decimal | None
    provider: str
    duration_ms: int


class SemanticMappingProvider(Protocol):
    def propose(
        self,
        source_system: str,
        schema_fingerprint: str,
        *,
        learning_preferences: list[dict[str, Any]] | None = None,
    ) -> MappingProposal | None: ...


class RecordedSemanticMappingProvider:
    """Uses explicit, versioned recorded model responses for local development and evaluation."""

    def __init__(self, fixture_directory: Path):
        self.fixture_directory = fixture_directory

    def propose(
        self,
        source_system: str,
        schema_fingerprint: str,
        *,
        learning_preferences: list[dict[str, Any]] | None = None,
    ) -> MappingProposal | None:
        # Recorded fixtures are immutable evidence. Production resolvers receive this same
        # non-authoritative context and may return a new proposal for human confirmation.
        del learning_preferences
        started_at = perf_counter()
        for fixture_path in self.fixture_directory.glob("*.json"):
            fixture = json.loads(fixture_path.read_text())
            if fixture["source_system"] == source_system and fixture["schema_fingerprint"] == schema_fingerprint:
                telemetry = fixture["telemetry"]
                return MappingProposal(
                    mapping=fixture["mapping"],
                    input_tokens=telemetry["input_tokens"],
                    output_tokens=telemetry["output_tokens"],
                    estimated_cost_usd=Decimal(telemetry["estimated_cost_usd"]),
                    provider=telemetry["provider"],
                    duration_ms=max(1, int((perf_counter() - started_at) * 1000)),
                )
        return None


class LangChainSemanticMappingProvider:
    """Uses LangChain and Google Gemini (gemini-3.1-flash-lite) to propose mappings for novel schemas."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.1-flash-lite",
        sample_payload: dict[str, Any] | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.sample_payload = sample_payload

    def propose(
        self,
        source_system: str,
        schema_fingerprint: str,
        *,
        learning_preferences: list[dict[str, Any]] | None = None,
    ) -> MappingProposal | None:
        del learning_preferences
        extractor = getattr(self, "extractor", None)
        if extractor is None:
            from app.domain.langchain_extractor import LangChainSemanticExtractor

            extractor = LangChainSemanticExtractor(api_key=self.api_key, model=self.model)
        try:
            return extractor.propose_schema_mapping(
                unmapped_payload=self.sample_payload or {},
                schema_fingerprint=schema_fingerprint,
                source_system=source_system,
            )
        except Exception:
            return None


class ChainedSemanticMappingProvider:
    """Evaluates providers in order until a proposal is returned."""

    def __init__(self, providers: list[SemanticMappingProvider]):
        self.providers = providers

    def propose(
        self,
        source_system: str,
        schema_fingerprint: str,
        *,
        learning_preferences: list[dict[str, Any]] | None = None,
    ) -> MappingProposal | None:
        for provider in self.providers:
            proposal = provider.propose(
                source_system,
                schema_fingerprint,
                learning_preferences=learning_preferences,
            )
            if proposal is not None:
                return proposal
        return None


def extract_source_metadata(payload: dict[str, Any]) -> tuple[str, str | None]:
    raw_meta = payload.get("meta")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    source_system = meta.get("source_system") or payload.get("source_system") or "unknown"
    schema_version = meta.get("export_version") or payload.get("schema_version")
    return str(source_system), str(schema_version) if schema_version is not None else None


def apply_mapping(payload: dict[str, Any], mapping: dict[str, Any], *, source_document: str) -> CanonicalQuotation:
    quotation_paths = mapping["quotation"]
    supplier_paths = mapping["supplier"]
    commercial_paths = mapping["commercial_terms"]
    def field(path_key: str) -> Any:
        source_path = quotation_paths.get(path_key)
        if source_path:
            return get_path(payload, source_path)
        return None

    quotation = CanonicalQuotation(
        quotation_reference=field("quotation_reference"),
        rfq_reference=field("rfq_reference"),
        document_type=field("document_type"),
        issue_date=field("issue_date"),
        valid_until=field("valid_until"),
        supplier=Supplier(
            **{canonical: get_path(payload, source_path) for canonical, source_path in supplier_paths.items()}
        ),
        commercial_terms=CommercialTerms(
            **{canonical: get_path(payload, source_path) for canonical, source_path in commercial_paths.items()}
        ),
        source={"document_name": source_document, "document_format": "json"},
    )
    for field_path, source_path in mapping.get("required_fields", {}).items():
        if get_path(payload, source_path) is None:
            quotation.review_issues.append(
                ReviewIssue(
                    field_path=field_path,
                    code="missing_required_source_value",
                    message="A required source value is absent; the canonical value remains null.",
                )
            )
    collection_path = mapping["line_items"]["collection_path"]
    collection = get_path(payload, collection_path.removesuffix("[]"))
    if not isinstance(collection, list):
        raise ValueError(f"Mapping collection path did not resolve to a list: {collection_path}")
    fields = mapping["line_items"]["fields"]
    for item in collection:
        def line(
            path_key: str,
            source_item: dict[str, Any] = item,
        ) -> Any:
            specification = fields.get(path_key)
            if specification:
                return resolve_mapping_value(source_item, specification)
            return None

        strengths = []
        strength_sources = fields.get("strength", {})
        for ingredient, source_path in strength_sources.items():
            value = scalar(item, source_path)
            if value is not None:
                strengths.append(Strength(ingredient=ingredient, value=as_decimal(value), unit="mg"))

        source_dosage_form = line("dosage_form")
        if isinstance(source_dosage_form, str):
            dosage_form, presentation = _core_dosage_form(source_dosage_form)
        else:
            dosage_form, presentation = source_dosage_form, None
        line_item = LineItem(
            source_key=line("source_key"),
            product=Product(
                trade_name=line("trade_name"),
                inn=line("inn") or [],
                strength=strengths,
                dosage_form=dosage_form,
                manufacturer=line("manufacturer"),
                country_of_origin=line("country_of_origin"),
            ),
            packaging=Packaging(
                description=line("pack_description"),
                presentation=presentation,
                primary_pack=line("primary_pack"),
                units_per_pack=line("units_per_pack"),
                unit_label=line("unit_label"),
                packs_per_shipper=line("packs_per_shipper"),
            ),
            quantity=Quantity(
                minimum_order_quantity=as_decimal(line("minimum_order_quantity")),
                minimum_order_quantity_uom=line("minimum_order_quantity_uom"),
            ),
            pricing=Pricing(
                currency=quotation.commercial_terms.currency,
                pack_price=as_decimal(line("pack_price")),
                quoted_price=QuotedPrice(
                    amount=as_decimal(line("quoted_price_amount")),
                    uom=line("quoted_price_uom"),
                ),
            ),
            supply=Supply(
                lead_time_days=line("lead_time_days"),
                shelf_life_months=line("shelf_life_months"),
                storage_conditions=line("storage_conditions"),
            ),
            regulatory=Regulatory(
                who_prequalified=line("who_prequalified"),
                who_pq_reference=line("who_pq_reference"),
                registered_markets=line("registered_markets") or [],
            ),
        )
        for field_path, source_path in mapping["line_items"].get("required_fields", {}).items():
            if scalar(item, source_path) is None:
                quotation.review_issues.append(
                    ReviewIssue(
                        field_path=f"line_items[{len(quotation.line_items)}].{field_path}",
                        code="missing_required_source_value",
                        message="A required source value is absent; the canonical value remains null.",
                    )
                )
        quotation.line_items.append(line_item)
    return quotation
