"""Deterministic, provenance-ready evidence access for semantic investigation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

WHOLE_SOURCE_CHARACTER_LIMIT = 16_000
CHUNK_CHARACTER_LIMIT = 4_000
DEFAULT_SEARCH_LIMIT = 6
MAX_ATLAS_CHUNKS = 60
TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_CHARACTER_LIMIT,
    chunk_overlap=0,
    add_start_index=True,
    strip_whitespace=False,
)


@dataclass(frozen=True)
class EvidenceChunk:
    """One addressable, deterministic fragment of a prepared source."""

    reference: str
    text: str
    kind: str
    metadata: dict[str, Any]

    def preview(self, length: int = 240) -> str:
        """Return a compact, whitespace-normalized discovery preview."""

        return " ".join(self.text.split())[:length]


# --- Section 1: Data Chunking & Search Term Extraction Helpers ---


def _terms(value: str) -> tuple[str, ...]:
    return tuple(term for term in re.findall(r"[\w.-]+", value.casefold()) if len(term) > 1)


def _json_chunks(payload: Any, path: str = "$") -> list[EvidenceChunk]:
    encoded = json.dumps(payload, default=str, sort_keys=True)
    if len(encoded) <= CHUNK_CHARACTER_LIMIT:
        return [EvidenceChunk(reference=f"json:{path}", text=encoded, kind="json_node", metadata={"path": path})]
    if isinstance(payload, list):
        chunks: list[EvidenceChunk] = []
        for index, item in enumerate(payload):
            chunks.extend(_json_chunks(item, f"{path}[{index}]"))
        return chunks
    if isinstance(payload, dict):
        chunks = []
        for key, item in payload.items():
            escaped = str(key).replace("\\", "\\\\").replace("'", "\\'")
            child_path = f"{path}.{key}" if str(key).replace("_", "").isalnum() else f"{path}['{escaped}']"
            chunks.extend(_json_chunks(item, child_path))
        return chunks
    return [EvidenceChunk(reference=f"json:{path}", text=encoded, kind="json_value", metadata={"path": path})]


def _page_chunks(pages: Any, *, prefix: str) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
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
        chunks.append(
            EvidenceChunk(
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
    return chunks


def _text_chunks(
    text: str,
    *,
    prefix: str,
    kind: str,
    metadata: dict[str, Any] | None = None,
) -> list[EvidenceChunk]:
    if not text:
        return []
    base_metadata = metadata or {}
    chunks = []
    for document in TEXT_SPLITTER.create_documents([text]):
        start = int(document.metadata["start_index"])
        end = start + len(document.page_content)
        chunks.append(
            EvidenceChunk(
                reference=f"{prefix}:{start}-{end}",
                text=document.page_content,
                kind=kind,
                metadata={**base_metadata, "start_offset": start, "end_offset": end},
            )
        )
    return chunks


def _chunks_for(source_type: str, context: dict[str, Any]) -> list[EvidenceChunk]:
    if source_type == "json" and isinstance(context.get("source_json"), dict):
        return _json_chunks(context["source_json"])
    if source_type == "pdf":
        return _page_chunks(context.get("pages", []), prefix="pdf")
    if source_type in {"ocr", "vision_direct", "ocr_assisted"}:
        return _page_chunks(context.get("pages", []), prefix="ocr")
    if source_type == "email":
        body = str(context.get("body_text", ""))
        return _text_chunks(body, prefix="email:body", kind="email_block")
    return _text_chunks(json.dumps(context, default=str, sort_keys=True), prefix="source", kind="source_text")


# --- Section 2: Unified Evidence Workspace ---


class EvidenceWorkspace:
    """Source-specific chunks behind a uniform search and inspection interface."""

    def __init__(self, *, source_type: str, chunks: tuple[EvidenceChunk, ...], mode: str):
        self.source_type = source_type
        self.chunks = chunks
        self.mode = mode
        self._by_reference = {chunk.reference: chunk for chunk in chunks}

    @classmethod
    def from_context(cls, source_type: str, context: dict[str, Any]) -> EvidenceWorkspace:
        """Create stable source references without changing parser output."""

        chunks = tuple(_chunks_for(source_type, context))
        characters = max(
            sum(len(chunk.text) for chunk in chunks),
            len(json.dumps(context, default=str, sort_keys=True)),
        )
        return cls(
            source_type=source_type,
            chunks=chunks,
            mode="whole_source" if characters <= WHOLE_SOURCE_CHARACTER_LIMIT else "retrieval",
        )

    def atlas(self) -> dict[str, Any]:
        """Expose source shape and references without sending every chunk body."""

        visible_chunks = self.chunks[:MAX_ATLAS_CHUNKS]
        return {
            "mode": self.mode,
            "source_type": self.source_type,
            "chunk_count": len(self.chunks),
            "omitted_chunk_count": len(self.chunks) - len(visible_chunks),
            "chunks": [
                {
                    "reference": chunk.reference,
                    "kind": chunk.kind,
                    "preview": chunk.preview(),
                    "metadata": chunk.metadata,
                }
                for chunk in visible_chunks
            ],
        }

    def search(
        self,
        query: str,
        *,
        references: list[str] | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> tuple[EvidenceChunk, ...]:
        """Return lexically and structurally relevant candidate fragments.

        This intentionally does not embed source data. A later embedding provider
        can participate in ranking, while exact source references stay unchanged.
        """

        query_terms = set(_terms(query))
        candidates = self._select(references)
        scored: list[tuple[int, EvidenceChunk]] = []
        for chunk in candidates:
            haystack = f"{chunk.reference} {chunk.kind} {chunk.text}".casefold()
            score = sum(term in haystack for term in query_terms)
            if query.casefold().strip() and query.casefold().strip() in haystack:
                score += len(query_terms) + 2
            if score:
                scored.append((score, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].reference))
        return tuple(chunk for _, chunk in scored[: max(1, min(limit, DEFAULT_SEARCH_LIMIT))])

    def inspect(self, references: list[str]) -> tuple[EvidenceChunk, ...]:
        """Resolve explicit source references in caller-specified order."""

        resolved: list[EvidenceChunk] = []
        seen: set[str] = set()
        for reference in references:
            chunk = self._resolve(reference)
            if chunk is not None and chunk.reference not in seen:
                resolved.append(chunk)
                seen.add(chunk.reference)
        return tuple(resolved)

    def has_reference(self, reference: str) -> bool:
        """Return whether one deterministic evidence reference exists."""

        return self._resolve(reference) is not None

    def references(self) -> tuple[str, ...]:
        """Return all stable evidence references."""

        return tuple(chunk.reference for chunk in self.chunks)

    def _select(self, references: list[str] | None) -> tuple[EvidenceChunk, ...]:
        if not references:
            return self.chunks
        selected: list[EvidenceChunk] = []
        seen: set[str] = set()
        for reference in references:
            chunk = self._resolve(reference)
            if chunk is not None and chunk.reference not in seen:
                selected.append(chunk)
                seen.add(chunk.reference)
        return tuple(selected)

    def _resolve(self, reference: str) -> EvidenceChunk | None:
        direct = self._by_reference.get(reference)
        if direct is not None:
            return direct
        if not reference.startswith("json:"):
            return None
        path = reference.removeprefix("json:")
        containing = [
            chunk
            for chunk in self.chunks
            if isinstance(chunk.metadata.get("path"), str) and path.startswith(chunk.metadata["path"])
        ]
        return max(containing, key=lambda chunk: len(str(chunk.metadata["path"])), default=None)
