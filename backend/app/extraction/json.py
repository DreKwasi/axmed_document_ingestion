"""Per-document JSON profiling, semantic extraction, and source validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator

from app.config import Config
from app.extraction.contracts import CanonicalQuotation

# --- Section 1: Source Fact Models & Extractor Protocols ---


class JsonSourceFact(BaseModel):
    """A quotation-relevant value recovered from one JSON source document.

    Attributes:
        label: Human-readable identifier for the fact (e.g., 'Unit Price', 'Product').
        value: Recovered scalar or collection value.
        source_path: Rooted JSONPath pointer where this fact resides (e.g., '$.items[0].price').
        extraction_method: Method used ('direct_json' or 'semantic_json').
        confidence: Decimal certainty score between 0.00 and 1.00.
        confidence_reason: Explanation of evidence backing the confidence score.
        canonical_field: Target field in the canonical quotation schema, if mapped.
        normalization_status: 'mapped' or 'unmapped'.
    """

    label: str
    value: Any
    source_path: str
    extraction_method: str = "direct_json"
    confidence: Decimal = Field(default=Decimal("1.00"), ge=Decimal("0"), le=Decimal("1"))
    confidence_reason: str = "Direct value verified against the JSON source."
    canonical_field: str | None = None
    normalization_status: str = "unmapped"

    @field_validator("source_path")
    @classmethod
    def require_json_path(cls, value: str) -> str:
        """Enforce standard root-prefixed JSONPath notation."""
        if not value.startswith("$"):
            raise ValueError("source_path must be a JSONPath beginning with '$'.")
        return value


class JsonSemanticExtraction(BaseModel):
    """The model result for one source document only; never a reusable mapping."""

    quotation: CanonicalQuotation = Field(default_factory=CanonicalQuotation)
    source_facts: list[JsonSourceFact] = Field(default_factory=list)


@dataclass(frozen=True)
class JsonExtractionProposal:
    """Extraction proposal packaged with execution telemetry and cost metrics."""

    extraction: JsonSemanticExtraction
    provider: str
    model: str | None
    prompt_version: str
    duration_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: Decimal | None = None


class JsonSemanticExtractor(Protocol):
    """Protocol for pluggable JSON semantic extraction strategies."""

    def extract(
        self,
        payload: dict[str, Any],
        profile: dict[str, Any],
        *,
        source_document: str,
        invalid_source_paths: list[str] | None = None,
    ) -> JsonExtractionProposal | None:
        """Extract quotation facts from an arbitrary JSON payload."""
        ...


# --- Section 2: Structural Profiling & Collection Inventory ---


def _json_type(value: Any) -> str:
    """Classify a Python primitive into standard JSON type names."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def profile_json(payload: Any) -> dict[str, Any]:
    """Create a lossless structural inventory without assigning source meaning.

    Traverses the JSON tree to build:
    1. `paths`: List of all paths with type descriptions and key summaries.
    2. `candidate_collections`: Array paths containing uniform object dictionaries
       (identifying potential quotation line-item tables).

    Args:
        payload: Parsed JSON root object or array.

    Returns:
        Dictionary with 'paths' and 'candidate_collections' metadata.
    """
    paths: list[dict[str, Any]] = []
    collections: list[dict[str, Any]] = []

    def walk(value: Any, path: str) -> None:
        # Traverse dictionary objects and record key lists
        if isinstance(value, dict):
            paths.append({"path": path, "type": "object", "keys": sorted(map(str, value.keys()))})
            for key, child in value.items():
                escaped = str(key).replace("\\", "\\\\").replace("'", "\\'")
                child_path = f"{path}.{key}" if str(key).replace("_", "").isalnum() else f"{path}['{escaped}']"
                walk(child, child_path)
            return

        # Traverse arrays and check if elements are candidate uniform object tables
        if isinstance(value, list):
            element_keys = sorted(
                {str(key) for item in value if isinstance(item, dict) for key in item.keys()}
            )
            entry = {"path": path, "type": "array", "length": len(value), "item_keys": element_keys}
            paths.append(entry)
            if value and all(isinstance(item, dict) for item in value):
                collections.append(entry)
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
            return

        # Terminal primitive leaf node
        paths.append({"path": path, "type": _json_type(value), "sample": value})

    walk(payload, "$")
    return {"paths": paths, "candidate_collections": collections}


# --- Section 3: Deterministic JSONPath Navigation & Resolution ---

_MISSING = object()


def resolve_json_path(payload: Any, path: str) -> Any:
    """Resolve the JSONPath subset emitted by the extraction contract.

    Supports:
    - Root paths: '$'
    - Dot notation: '$.supplier.name'
    - Array indices: '$.items[0].price'
    - Bracketed quoted keys: '$[\'quoted-key\']'

    Returns:
        The matched value from the payload, or private sentinel `_MISSING` if not found.
    """
    if path == "$":
        return payload
    if not path.startswith("$"):
        return _MISSING
    current = payload
    index = 1
    while index < len(path):
        if path[index] == ".":
            index += 1
            start = index
            while index < len(path) and path[index] not in ".[":
                index += 1
            key = path[start:index]
            if not key or not isinstance(current, dict) or key not in current:
                return _MISSING
            current = current[key]
        elif path[index] == "[":
            close = path.find("]", index)
            if close == -1:
                return _MISSING
            token = path[index + 1 : close]
            # Numeric array index (e.g. [0])
            if token.isdigit():
                if not isinstance(current, list) or int(token) >= len(current):
                    return _MISSING
                current = current[int(token)]
            # Quoted dictionary key (e.g. ['complex-key'])
            elif len(token) >= 2 and token[0] == token[-1] == "'":
                key = token[1:-1].replace("\\'", "'").replace("\\\\", "\\")
                if not isinstance(current, dict) or key not in current:
                    return _MISSING
                current = current[key]
            else:
                return _MISSING
            index = close + 1
        else:
            return _MISSING
    return current


# --- Section 4: Grounded Source Fact Validation & Equivalence Checks ---


def _same_json_value(source: Any, extracted: Any) -> bool:
    """Compare JSON values tolerating numeric representation differences (e.g. float vs Decimal)."""
    if isinstance(source, bool) or isinstance(extracted, bool):
        return source is extracted
    if isinstance(source, int | float) and isinstance(extracted, int | float | Decimal | str):
        try:
            return Decimal(str(source)) == Decimal(str(extracted))
        except Exception:  # pragma: no cover - defensive at a provider boundary.
            return False
    return source == extracted


def validate_source_facts(
    payload: dict[str, Any], facts: list[JsonSourceFact]
) -> tuple[list[JsonSourceFact], list[str]]:
    """Keep grounded facts and identify claims that should be retried.

    Validates that:
    1. The declared JSONPath actually resolves within the source document.
    2. Direct JSON facts exactly match the source values (numeric/string equality).
    3. Normalization statuses ('mapped' vs 'unmapped') are synchronized.

    Args:
        payload: Original JSON payload.
        facts: Candidate extracted source facts.

    Returns:
        Tuple of (valid_facts, invalid_source_paths).
    """
    valid: list[JsonSourceFact] = []
    invalid_paths: list[str] = []
    for fact in facts:
        source_value = resolve_json_path(payload, fact.source_path)
        if source_value is _MISSING:
            invalid_paths.append(fact.source_path)
            continue
        if fact.extraction_method == "direct_json" and not _same_json_value(source_value, fact.value):
            invalid_paths.append(fact.source_path)
            continue
        fact.normalization_status = "mapped" if fact.canonical_field else "unmapped"
        valid.append(fact)
    return valid, invalid_paths


# --- Section 5: Extractor Implementations ---


class RecordedJsonSemanticExtractor:
    """Immutable recorded extraction responses for the offline test/eval path.

    Fixtures match the complete source content hash. They never map one source
    structure onto another and therefore are not schema memory.
    """

    def __init__(self, fixture_directory: Path):
        self.fixture_directory = fixture_directory

    def extract(
        self,
        payload: dict[str, Any],
        profile: dict[str, Any],
        *,
        source_document: str,
        invalid_source_paths: list[str] | None = None,
    ) -> JsonExtractionProposal | None:
        del profile, source_document, invalid_source_paths
        started = perf_counter()
        content_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        for fixture_path in self.fixture_directory.glob("*.json"):
            fixture = json.loads(fixture_path.read_text())
            if fixture.get("content_sha256") != content_hash:
                continue
            telemetry = fixture.get("telemetry", {})
            return JsonExtractionProposal(
                extraction=JsonSemanticExtraction.model_validate(fixture["extraction"]),
                provider=str(telemetry.get("provider", "recorded-json-extraction")),
                model=telemetry.get("model"),
                prompt_version=str(telemetry.get("prompt_version", "recorded-json-extraction-v1")),
                duration_ms=max(1, int((perf_counter() - started) * 1000)),
                input_tokens=telemetry.get("input_tokens"),
                output_tokens=telemetry.get("output_tokens"),
                estimated_cost_usd=(
                    Decimal(str(telemetry["estimated_cost_usd"]))
                    if telemetry.get("estimated_cost_usd") is not None
                    else None
                ),
            )
        return None


class LangChainJsonSemanticExtractor:
    """Adapter for the live LangChain semantic extraction provider chain."""

    def __init__(self, settings: Config):
        self.settings = settings

    def extract(
        self,
        payload: dict[str, Any],
        profile: dict[str, Any],
        *,
        source_document: str,
        invalid_source_paths: list[str] | None = None,
    ) -> JsonExtractionProposal | None:
        from app.extraction.llm import extract_semantics

        result = extract_semantics(
            self.settings,
            {
                "source_document": source_document,
                "structural_inventory": profile,
                "source_json": payload,
                "invalid_source_paths_from_previous_attempt": invalid_source_paths or [],
            },
            source_type="json",
        )
        from app.extraction.llm import aggregate_agent_telemetry

        telemetry = aggregate_agent_telemetry(result)
        return JsonExtractionProposal(
            extraction=JsonSemanticExtraction(
                quotation=result.quotation,
                source_facts=list(result.source_facts),
            ),
            provider=str(telemetry.get("provider", "google-gemini")),
            model=telemetry.get("model"),
            prompt_version=str(telemetry.get("prompt_version", "json-semantic-extraction-v1")),
            duration_ms=int(telemetry["duration_ms"]),
            input_tokens=telemetry.get("input_tokens"),
            output_tokens=telemetry.get("output_tokens"),
            estimated_cost_usd=telemetry.get("estimated_cost_usd"),
        )


class ChainedJsonSemanticExtractor:
    """Composite extractor evaluating a prioritized fallback chain of extractors."""

    def __init__(self, extractors: list[JsonSemanticExtractor]):
        self.extractors = extractors

    def extract(self, payload: dict[str, Any], profile: dict[str, Any], **kwargs: Any) -> JsonExtractionProposal | None:
        for extractor in self.extractors:
            proposal = extractor.extract(payload, profile, **kwargs)
            if proposal is not None:
                return proposal
        return None
