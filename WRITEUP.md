# Axmed Supplier Document Intelligence: Architecture & Implementation Narrative

## Executive summary

Axmed receives pharmaceutical supplier quotations as structured JSON, native PDFs, email correspondence, and degraded scans. The system preserves each source, prepares a format-appropriate representation, uses semantic reasoning only where interpretation is required, validates commercial relationships in ordinary code, and requires a human decision before approval or rejection.

The implementation follows six boundaries:

1. **Source truth before normalization.** Supplier-stated values and evidence remain distinct from calculated values.
2. **Per-document semantic extraction.** JSON documents are interpreted independently; the system does not learn or reuse supplier-schema mappings.
3. **Deterministic controls.** Media validation, source-path checks, commercial calculations, persistence, confidence policy, and review transitions remain application responsibilities.
4. **Explicit uncertainty.** Ambiguous values remain unmapped or become targeted mapping issues rather than guesses.
5. **Privacy-aware preparation.** Contact information is removed from text sent to providers; image pixels remain an explicit external-provider boundary.
6. **Human authority.** Every successful quotation enters `pending_review`; only a reviewer can approve, reject, or correct it.

## Current architecture

```text
Vue review workspace
        │ REST + SSE
        ▼
FastAPI application
        ├── upload validation and safe source persistence
        ├── API-owned document background tasks
        ├── format-specific preparation and semantic extraction
        ├── deterministic validation and commercial rules
        └── human-review commands
        │
        ▼
SQLite WAL
        ├── documents and stored source references
        ├── quotations and normalized line items
        ├── source facts and field evidence
        ├── processing events and model invocations
        └── review and evaluation records
```

The take-home uses one FastAPI process, API-owned Python background tasks, one SQLite database, and reconnectable Server-Sent Events. There is no Huey worker, separate task database, stored batch entity, or schema-mapping table in the current implementation. Multi-file upload results are independent document records, so one failure does not invalidate successful siblings.

## Ingestion paths

### Structured JSON

The application parses and profiles each JSON document in memory. Semantic extraction returns a canonical candidate plus quotation-relevant source facts. Direct claims must resolve to exact JSONPaths and match their source values. Invalid claims receive one corrective attempt; valid facts are retained. Facts whose meaning is clear but whose canonical destination is uncertain remain stored as `unmapped`.

Recorded responses keyed to an exact source-content hash keep offline tests deterministic. They are fixtures, not reusable mappings, and do not create a zero-model path for similarly shaped documents.

### Supplier email

The MIME parser extracts safe text without rendering active HTML. It removes greetings, signatures, contact details, and repeated bodies before semantic extraction. Explicit later corrections are reconciled against the structured result only when item, amount, and commercial basis agree.

### Native PDF

LiteParse produces native reading-order text, table geometry, page boundaries, and quality signals in process. The semantic agent interprets the complete prepared representation, including tables, notes, footnotes, and narrative. There is no separate narrative-enrichment call.

### Images and scanned documents

PaddleOCR supplies text, confidence, and geometry. A configurable quality gate prevents semantic extraction when the source is too weak. For accepted images, OCR-assisted text and masked visual regions create separate extraction attempts; neither automatically overrides the other. Pixel content is treated as an explicit provider privacy boundary because it cannot be text-redacted reliably.

## Commercial rules and provenance

Deterministic rules run after semantic interpretation. They preserve quoted price and quantity bases, derive a normalized price only from established facts, record formulas and validation status, and never present a calculation as supplier evidence.

```text
EUR 3.15 / pack          source value
90 tablets / pack        source value
EUR 0.035 / tablet       derived value with formula and validation status
```

Field evidence is reserved for real source excerpts/locations and human actions. An internal transformation path is lineage, not proof that the supplier stated a value.

## Confidence and review

Extraction confidence answers whether the source was recovered faithfully. Mapping confidence answers whether a recovered value was assigned to the correct canonical field. They remain separate from completeness and approval.

The application calculates confidence from observable signals such as source readability, OCR quality, JSONPath grounding, row/cell association, provenance, deterministic reconciliation, and conflicts. Model self-assessment is not accepted as the confidence policy. Every reviewable result still requires a human decision.

## Bounded semantic investigation

Semantic extraction uses a bounded, document-scoped LangChain agent within background processing:

```text
Prepared source and format capabilities
        ↓
Build stable evidence references and source atlas
        ↓
Propose canonical assignments with evidence
        ↓
Search and inspect related evidence when more context is needed
        ↓
Deterministic path, value, reference, completeness, and commercial checks
        ↓
Re-investigate while feedback changes and execution budgets remain
        ↓
Finalize candidate or emit targeted unresolved issues
```

The application continues to detect media type and select parsers deterministically. The semantic component receives the relevant capabilities—JSON paths and sibling context, PDF pages/cells/regions, sanitized email chronology, or accepted OCR text and masked image regions—and chooses only what additional evidence to inspect when meaning is ambiguous.

Canonical field knowledge should describe meaning, types, required context, related fields, common confusions, permitted derivations, evidence requirements, contradictions, and review triggers. It is guidance for interpreting one document, not an exhaustive source-key list or learned supplier mapping.

`search_evidence`, `inspect_evidence`, and `validate_candidate` are the agent's only investigation capabilities. The first two operate over deterministic chunks with source references: JSON nodes, PDF/OCR page-text spans, and email-body spans. Small inputs are supplied whole; large inputs receive a compact atlas and fetch only relevant fragments. The active ranker is lexical/structural, not embedding-backed. An embedding ranker can later improve retrieval over the same chunks without changing their provenance contract.

The active loop has model-call, per-tool, evidence-volume, wall-clock, and provider-timeout bounds. Intermediate hypotheses remain execution state and never enter quotation state. Unresolved material conflicts go to human review; the semantic component cannot approve a document or override deterministic validation. LangGraph remains a future orchestration option if explicit persisted and operator-tweakable investigation state becomes necessary.

## Synchronous and background boundaries

The boundary is based on latency and external-resource risk, not simply whether code is deterministic.

The synchronous request path validates the upload, verifies media type, persists the source and processing record, performs inexpensive preparation, schedules unpredictable work, and returns a document identifier. Background processing owns expensive parsing or OCR, semantic investigation, post-extraction validation and derivation, confidence calculation, and persistence of the review-ready result. Fast deterministic operations that depend on semantic output remain in the background job immediately after extraction.

PDF, email, image, and JSON semantic work all runs after the source record is persisted. The local implementation uses API-owned background tasks; a production deployment would use a durable queue or workflow runtime.

## Security and operations

Uploads are checked by extension and media signature, stored under generated names, and processed under configured size and quality limits. Logs, events, diagnostics, and recorded model metadata exclude raw source content and contact PII. SQLite is suitable for the local take-home; production scale would move durable records to managed PostgreSQL, source files to object storage, and document jobs to a durable queue or workflow service.

## Evaluation

Normal CI uses recorded adapters and deterministic fixtures; it does not require provider credentials or network access. Live evaluations separately record provider, model, prompt version, duration, token use, estimated cost, canonical diffs, and safe failure analysis. The evaluation corpus covers structured JSON, email correction chronology, native PDFs, OCR sources, commercial calculations, provenance, and seeded-PII leakage checks.

## Deliberate limits

- No model-directed file routing or parser selection.
- No reusable supplier-schema mapping or automatic bypass of semantic interpretation.
- No separate model call for every field.
- No universal hand-built PDF table reconstruction.
- No OCR of clean native PDF pages merely for uniformity.
- No unsupported certainty or automatic approval.
- No medicine-catalogue retrieval layer unless product matching becomes a demonstrated requirement.
