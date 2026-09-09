"""Per-document JSON profiling, semantic extraction, and source validation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
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


DEFAULT_MAX_DEPTH = 20
DEFAULT_MAX_PATHS = 500
DEFAULT_MAX_ARRAY_SAMPLES = 3
DEFAULT_MAX_KEYS_PER_OBJECT = 100


def profile_json(
    payload: Any,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_paths: int = DEFAULT_MAX_PATHS,
    max_array_samples: int = DEFAULT_MAX_ARRAY_SAMPLES,
    max_keys_per_object: int = DEFAULT_MAX_KEYS_PER_OBJECT,
) -> dict[str, Any]:
    """Create a bounded structural inventory without assigning source meaning.

    Iteratively traverses the JSON tree with depth, path-count, and array-sample bounds to:
    1. Prevent RecursionError on deeply nested payloads.
    2. Prevent O(N) path and token blowouts on large arrays/collections by sampling items.
    3. Build:
       - `paths`: List of paths with type descriptions and key summaries.
       - `candidate_collections`: Array paths containing uniform object dictionaries
         (identifying potential quotation line-item tables).

    Args:
        payload: Parsed JSON root object or array.
        max_depth: Maximum depth to traverse before truncating child expansion.
        max_paths: Maximum number of path entries to collect before stopping.
        max_array_samples: Maximum number of array elements to traverse for schema inspection.
        max_keys_per_object: Maximum number of keys per dictionary to inspect.

    Returns:
        Dictionary with 'paths' and 'candidate_collections' metadata.
    """
    paths: list[dict[str, Any]] = []
    collections: list[dict[str, Any]] = []

    # Iterative DFS stack storing: (value, path, depth)
    stack: list[tuple[Any, str, int]] = [(payload, "$", 0)]

    while stack and len(paths) < max_paths:
        value, path, depth = stack.pop()

        if isinstance(value, dict):
            sorted_items = sorted(value.items(), key=lambda item: str(item[0]))
            raw_keys = [str(k) for k, _ in sorted_items]
            truncated_keys = raw_keys[:max_keys_per_object]

            entry: dict[str, Any] = {"path": path, "type": "object", "keys": truncated_keys}
            if len(raw_keys) > max_keys_per_object:
                entry["total_keys"] = len(raw_keys)
            paths.append(entry)

            if depth < max_depth and len(paths) < max_paths:
                # Push children in reverse order so first keys are popped first (DFS pre-order)
                for key, child in reversed(sorted_items[:max_keys_per_object]):
                    escaped = str(key).replace("\\", "\\\\").replace("'", "\\'")
                    child_path = f"{path}.{key}" if str(key).replace("_", "").isalnum() else f"{path}['{escaped}']"
                    stack.append((child, child_path, depth + 1))
            continue

        if isinstance(value, list):
            sample_for_keys = value[: min(len(value), 50)]
            element_keys = sorted(
                {str(key) for item in sample_for_keys if isinstance(item, dict) for key in item.keys()}
            )
            sampled_count = min(len(value), max_array_samples)
            arr_entry: dict[str, Any] = {
                "path": path,
                "type": "array",
                "length": len(value),
                "item_keys": element_keys,
            }
            if len(value) > max_array_samples:
                arr_entry["sampled_elements"] = sampled_count

            paths.append(arr_entry)

            # Uniform object candidate collection check
            if value and all(isinstance(item, dict) for item in sample_for_keys):
                coll_entry = dict(arr_entry)
                coll_entry["element_path_pattern"] = f"{path}[*]"
                collections.append(coll_entry)

            if depth < max_depth and len(paths) < max_paths:
                # Push sampled array items in reverse order
                for index in reversed(range(sampled_count)):
                    stack.append((value[index], f"{path}[{index}]", depth + 1))
            continue

        # Terminal primitive leaf node
        paths.append({"path": path, "type": _json_type(value), "sample": value})

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


def resolve_existing_json_path(payload: Any, path: str) -> tuple[bool, Any]:
    """Resolve a JSONPath while keeping a legitimate JSON null distinct from a missing path."""

    value = resolve_json_path(payload, path)
    return (False, None) if value is _MISSING else (True, value)


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
    ) -> JsonExtractionProposal | None:
        from app.extraction.llm import extract_semantics

        result = extract_semantics(
            self.settings,
            {
                "source_document": source_document,
                "structural_inventory": profile,
                "source_json": payload,
            },
            source_type="json",
        )
        from app.extraction.llm import aggregate_semantic_telemetry

        telemetry = aggregate_semantic_telemetry(result)
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
