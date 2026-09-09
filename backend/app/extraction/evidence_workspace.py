"""Deterministic, provenance-ready evidence access for semantic investigation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

WHOLE_SOURCE_CHARACTER_LIMIT = 10_000_000
CHUNK_CHARACTER_LIMIT = 10_000_000
DEFAULT_SEARCH_LIMIT = 6


@dataclass(frozen=True)
class EvidenceItem:
    """One addressable, deterministic item of a prepared source document."""

    reference: str
    text: str
    kind: str
    metadata: dict[str, Any]

    def preview(self, length: int = 240) -> str:
        """Return a compact, whitespace-normalized discovery preview."""

        return " ".join(self.text.split())[:length]


# --- Section 1: Search Term Extraction & Document Items ---


def _terms(value: str) -> tuple[str, ...]:
    return tuple(term for term in re.findall(r"[\w.-]+", value.casefold()) if len(term) > 1)


def _json_items(payload: Any, path: str = "$") -> list[EvidenceItem]:
    encoded = json.dumps(payload, default=str, sort_keys=True)
    return [EvidenceItem(reference=f"json:{path}", text=encoded, kind="json", metadata={"path": path})]


def _page_items(pages: Any, *, prefix: str) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for fallback_page, page in enumerate(pages if isinstance(pages, list) else [], start=1):
        if not isinstance(page, dict):
            continue
        page_number = page.get("page_number", fallback_page)
        text = str(page.get("text", ""))
        layout = page.get("liteparse")
        page_payload: dict[str, Any] = {"text": text}
        if layout is not None:
            page_payload["native_layout"] = layout
        page_text = json.dumps(page_payload, default=str, sort_keys=True)
        items.append(
            EvidenceItem(
                reference=f"{prefix}:page:{page_number}",
                text=page_text,
                kind="page",
                metadata={
                    "page_number": page_number,
                    "start_offset": 0,
                    "end_offset": len(page_text),
                    "atomic": True,
                    "has_native_layout": layout is not None,
                },
            )
        )
    return items


def _text_items(
    text: str,
    *,
    prefix: str,
    kind: str,
    metadata: dict[str, Any] | None = None,
) -> list[EvidenceItem]:
    if not text:
        return []
    base_metadata = metadata or {}
    return [
        EvidenceItem(
            reference=f"{prefix}:0-{len(text)}",
            text=text,
            kind=kind,
            metadata={**base_metadata, "start_offset": 0, "end_offset": len(text)},
        )
    ]


def _items_for(source_type: str, context: dict[str, Any]) -> list[EvidenceItem]:
    if source_type == "json" and isinstance(context.get("source_json"), dict):
        return _json_items(context["source_json"])
    if source_type == "pdf":
        return _page_items(context.get("pages", []), prefix="pdf")
    if source_type in {"ocr", "vision_direct", "ocr_assisted"}:
        return _page_items(context.get("pages", []), prefix="ocr")
    if source_type == "email":
        body = str(context.get("body_text", ""))
        return _text_items(body, prefix="email:body", kind="email_body")
    return _text_items(json.dumps(context, default=str, sort_keys=True), prefix="source", kind="source_text")


# --- Section 2: Unified Evidence Workspace ---


class EvidenceWorkspace:
    """Source-specific evidence representations behind a uniform search and inspection interface."""

    def __init__(self, *, source_type: str, items: tuple[EvidenceItem, ...], mode: str = "whole_source"):
        self.source_type = source_type
        self.items = items
        self.mode = mode
        self._by_reference = {item.reference: item for item in items}

    @classmethod
    def from_context(cls, source_type: str, context: dict[str, Any]) -> EvidenceWorkspace:
        """Create stable source references without chunking or splitting."""

        items = tuple(_items_for(source_type, context))
        return cls(
            source_type=source_type,
            items=items,
            mode="whole_source",
        )

    def atlas(self) -> dict[str, Any]:
        """Expose source document structure and references without chunking."""

        return {
            "mode": self.mode,
            "source_type": self.source_type,
            "item_count": len(self.items),
            "items": [
                {
                    "reference": item.reference,
                    "kind": item.kind,
                    "preview": item.preview(),
                    "metadata": item.metadata,
                }
                for item in self.items
            ],
        }

    def search(
        self,
        query: str,
        *,
        references: list[str] | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> tuple[EvidenceItem, ...]:
        """Return lexically and structurally relevant candidate evidence items."""

        query_terms = set(_terms(query))
        candidates = self._select(references)
        scored: list[tuple[int, EvidenceItem]] = []
        for item in candidates:
            haystack = f"{item.reference} {item.kind} {item.text}".casefold()
            score = sum(term in haystack for term in query_terms)
            if query.casefold().strip() and query.casefold().strip() in haystack:
                score += len(query_terms) + 2
            if score:
                scored.append((score, item))
        scored.sort(key=lambda entry: (-entry[0], entry[1].reference))
        return tuple(item for _, item in scored[: max(1, min(limit, DEFAULT_SEARCH_LIMIT))])

    def inspect(self, references: list[str]) -> tuple[EvidenceItem, ...]:
        """Resolve explicit source references in caller-specified order."""

        resolved: list[EvidenceItem] = []
        seen: set[str] = set()
        for reference in references:
            item = self._resolve(reference)
            if item is not None and item.reference not in seen:
                resolved.append(item)
                seen.add(item.reference)
        return tuple(resolved)

    def has_reference(self, reference: str) -> bool:
        """Return whether one deterministic evidence reference exists."""

        return self._resolve(reference) is not None

    def references(self) -> tuple[str, ...]:
        """Return all stable evidence references."""

        return tuple(item.reference for item in self.items)

    def _select(self, references: list[str] | None) -> tuple[EvidenceItem, ...]:
        if not references:
            return self.items
        selected: list[EvidenceItem] = []
        seen: set[str] = set()
        for reference in references:
            item = self._resolve(reference)
            if item is not None and item.reference not in seen:
                selected.append(item)
                seen.add(item.reference)
        return tuple(selected)

    def _resolve(self, reference: str) -> EvidenceItem | None:
        direct = self._by_reference.get(reference)
        if direct is not None:
            return direct
        if reference.startswith("json:"):
            path = reference.removeprefix("json:")
            containing = [
                item
                for item in self.items
                if isinstance(item.metadata.get("path"), str) and path.startswith(item.metadata["path"])
            ]
            return max(containing, key=lambda item: len(str(item.metadata["path"])), default=None)
        prefix_match = re.match(r"^(.*?):(\d+)-(\d+)$", reference)
        for item in self.items:
            item_match = re.match(r"^(.*?):(\d+)-(\d+)$", item.reference)
            if prefix_match:
                item_prefix = item_match.group(1) if item_match else item.reference
                if prefix_match.group(1) == item_prefix:
                    start, end = int(prefix_match.group(2)), int(prefix_match.group(3))
                    item_end = int(item_match.group(3)) if item_match else len(item.text)
                    if 0 <= start <= end <= item_end:
                        return item
                    return None
            if item.reference == reference or item.reference.startswith(f"{reference}:"):
                return item
        return None
