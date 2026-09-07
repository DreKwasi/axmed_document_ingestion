# Supplier Document Intelligence — Implementation Plan

> Purpose: turn the Axmed document-intelligence PRD into an executable, take-home-sized delivery plan.
> Status: approved for full scope; publish dependency-ordered work into `TODOS.md` before implementation.
> Strategy: ship tracer-bullet vertical slices, each demoable through the running FastAPI and Vue application.
> Critical thesis: each JSON source is independently profiled and semantically extracted; canonical normalization never discards a correctly recovered source fact.
> Trust boundary: every successful extraction enters human review; confidence prioritizes attention but never auto-approves a record. Missing commercial values remain separate availability exceptions.
> Source: `docs/product/axmed_document_intelligence_prd.md` and the checked-in synthetic corpus in `sample_documents/`.

## 1. Outcome and scope

The finished take-home should demonstrate one coherent workflow:

1. Upload one or more supplier documents.
2. Observe durable processing progress.
3. Receive a canonical quotation with original commercial meaning intact.
4. See derived values, uncertainty, validation issues, and source evidence separately.
5. Route exceptions to review, then correct, approve, or reject the result with an auditable outcome.
6. Re-extract a retained JSON source explicitly without changing its human-review audit history.

### Required product stories

- **US-01 — Ingest:** A procurement user can upload JSON, EML, PDF, PNG, or JPEG supplier documents and receive an explicit accepted/rejected result.
- **US-02 — Track:** A user can see each document move through processing stages and can reconnect without losing work.
- **US-03 — Review:** A reviewer can inspect canonical quotation lines, prioritized uncertainty, source-versus-derived values, and evidence.
- **US-04 — Decide:** A reviewer can correct fields and approve or reject a quotation; accepted state is never inferred from extraction success.
- **US-05 — Preserve:** A JSON fact with uncertain canonical normalization remains a successful, source-grounded extracted fact.
- **US-06 — Operate:** An engineer can diagnose failures and compare parse, OCR, PII, model, and total latency without raw document text in logs.
- **US-07 — Evaluate:** An evaluator can run the supplied corpus against checked-in ground truth and inspect field-level accuracy and cost.

### Deliberate cut line

The delivery scope includes every supplied format (JSON, email, native PDF, and degraded images), live PaddleOCR on Modal, batch upload, corpus evaluation, and final documentation. The take-home does not build production RBAC, distributed storage/queues, enterprise audit retention, or broad multilingual support; it documents their production implications instead. Deployment itself remains a user-authorized action when Slice 6 is ready.

## 2. Proposed technical baseline

### Repository and runtime

- Monorepo with `backend/` (including `backend/evals/`), `frontend/`, `sample_documents/`, and `data/` (ignored runtime state).
- Python 3.12 managed by `uv`; FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, pytest, Ruff, and mypy.
- Vue 3, Vite, and TypeScript with Vitest, Vue Testing Library, and Playwright.
- `app.db` for application state. Enable WAL and keep background-task writes short.
- One documented command starts API and frontend; one command runs the full validation suite.

Python 3.12 is a useful compatibility target because current Presidio guidance supports it. LiteParse is recent and should sit behind a parser adapter with a one-slice feasibility gate. API-owned Python background tasks keep the current local runtime simple; a later production queue must include bounded calls and stale-job recovery.

### Backend boundaries

Keep orchestration independent of vendors through small ports:

```text
DocumentPipeline
├── StructuredIngest     JSON profiling + per-document semantic fact extraction
├── UnstructuredParsers  MIME | LiteParse | PaddleOCR
├── ParseQualityPolicy   native text/table quality and OCR decision
├── OcrClient            Modal PaddleOCR | fixture fake
├── PiiRedactor          Presidio
├── SemanticExtractor    LangChain structured output | fixture fake
├── QuotationRules       normalization, calculations, validation, confidence
└── ReviewService        correction, approval, rejection
```

The pipeline owns stage transitions; adapters do not mutate review state directly.

### Persistence model

Use relational tables for operational state and versioned JSON for the evolving canonical payload:

- `documents`: identity, file metadata, type, status, and failure reason.
- `document_artifacts`: native parse, OCR parse, and redacted model input with storage references and quality metadata.
- `quotations`: canonical payload, schema version, current review status, revision.
- `field_evidence`: JSON-pointer field path, source location/page/bounds/snippet, method, confidence, supersession link.
- `processing_events`: monotonic ID, document ID, stage, safe metadata, timestamp; source for SSE.
- `reviews`: action, field patches, reviewer note, prior/new revision, timestamp.
- `extracted_source_facts`: every quotation-relevant JSON fact, including raw value, JSONPath, method, confidence, normalization status, optional canonical field, and inherited review status.
- `model_invocations`: operation, model, prompt/schema version, token counts, duration, estimated cost; never raw sensitive input.

Keep business values readable in the canonical payload. Store provenance separately by field path rather than wrapping every scalar. Derived values still carry their calculation and `derived: true` marker in the payload.

### Canonical contract and ground truth

Version the canonical Pydantic model before the first parser. Its MVP must include quotation type/reference/dates, supplier, currency and commercial terms, line items, product identity with paired ingredient strengths, original packaging description, quoted quantity versus MOQ, quoted price and basis, price tiers/adjustments, normalized price, supply details, regulatory fields, and source metadata. The first UI may show a subset, but parsers must not silently discard supported values.

Unknown canonical values remain `null`; they never mean an empty string, zero, or model guess. A correctly recovered fact with no certain canonical destination is stored separately without a review issue or confidence penalty. Use `Decimal` for money and explicit units.

Check in a corpus manifest from Slice 1. For each fixture it names the document class, expected fields, intentionally unreadable/unknown fields, expected review issues, and comparison mode: exact, normalized text, decimal tolerance, ordered/unordered collection, or null correctness.

### JSON extraction contract

Each JSON upload is profiled in memory and then semantically extracted without cross-document memory. Facts carry raw value, JSONPath, method, confidence, rationale, normalization status, and optional canonical field. Direct JSON facts are accepted only when resolving their JSONPath produces the claimed value; invalid claims cause one retry while already validated facts remain.

No schema fingerprint, stored mapping, alias-learning record, mapping confirmation, or automatic reuse is part of the current product. Mapping uncertainty does not affect extraction confidence. Only source readability, ambiguity, conflicts, and pointer/value validation do. A document fails only when no meaningful quotation facts are recovered.

### State and trust model

Keep processing and the human review lifecycle separate:

```text
processing:    received → parsed → queued → processing → terminal | failed
review status: pending_review → approved | rejected
```

Per-field source clarity, association certainty, independent validation, conflicts, and OCR/parser warnings classify confidence without averaging. Derived values keep formula and validation status and receive no extraction-confidence band. Every successful source enters `pending_review`; the review queue contains all of them. Approval requires no note. A correction is an audited action with before/after patches that preserves `pending_review` until explicit approval, then sets `has_corrections`. Rejection requires one structured reason (`unreadable_source`, `incorrect_extraction`, `unsupported_document`, `duplicate`, `not_a_quotation`, or `other`) and may include a note. Commands are idempotent by request key and stale revisions conflict.

### Local data and privacy boundary

Classify data before implementation:

- Raw documents and unredacted snippets: local restricted source/evidence path only.
- Redacted model input: persisted only when needed for debugging/evaluation and never mixed with raw artifacts.
- Canonical commercial records: reviewer-visible; may retain supplier/company identity.
- Events, logs, exceptions, telemetry, fixtures, screenshots, and reports: safe metadata only; no raw text, personal email/phone/name, banking/account identifiers, or unrelated addresses.

Validate media signatures as well as extensions, impose upload/page/text limits, generate safe storage names, contain parser failures, and never render active email HTML. Seeded-PII tests must cover model payloads, logs, SSE, exceptions, reports, and recorded fixtures while proving allowed company identity remains.

## 3. Vertical implementation slices

### Slice 1 — Prove source-grounded JSON extraction in one runnable path

**Blocked by:** None  
**Covers:** US-01, US-03, US-05, US-07

Build the walking skeleton and the product’s core thesis together: FastAPI, minimal Vue review screen, SQLite migrations, versioned canonical contract, corpus manifest, safe upload, recursive JSON profiling, a recorded semantic fact extractor, JSONPath/value validation, and extracted-source-fact persistence. Use nested, flat, and mixed JSON fixtures.

Acceptance checks:

- A fresh checkout installs, migrates, and starts the backend/frontend with one documented command.
- First upload produces source-grounded facts and only the canonical fields that can be normalized with certainty.
- Nested, flat, and mixed JSON structures do not influence one another.
- `$.order_info.minimum = "5,000 boxes"` persists as a high-confidence unmapped fact while canonical fields remain blank.
- Invalid pointers trigger a retry, partial-success results retain valid facts, and only no-meaningful-fact results fail.
- Media signature/size/name protections, canonical null semantics, and the Sanova manifest are tested.

### Slice 2 — Add deterministic commercial rules, evidence, and review decisions

**Blocked by:** Slice 1  
**Covers:** US-03, US-04, US-07

Complete the Sanova quotation path with price normalization, validation, field evidence, confidence/issues, correction revisions, approval, and rejection. Retain the supplier’s pack price while deriving unit price with `Decimal` arithmetic. This slice supports multiple selected JSON documents; the PRD's EML/PDF/image router arrives with their parser slices.

Acceptance checks:

- Review UI separates quoted and derived price, shows formula/source path, and prioritizes failed validations.
- Corrections retain prior evidence and remain unapproved until an explicit approval; they never teach a later source-schema interpretation.
- Approve/reject/correct commands are idempotent; stale revisions conflict; failed or stale records cannot be accepted downstream.
- Tests cover arithmetic, quantities versus MOQ, invalid dates/percentages/tiers, source-fact validation, and review transitions.
- One ingest action accepts multiple documents and preserves independent review state/source access for each; a Playwright test uploads, corrects a field, and approves the current revision.

### Slice 3 — Add durable jobs and reconnectable live progress

**Blocked by:** Slice 2  
**Covers:** US-02, US-06

Move unpredictable processing into API-owned Python background tasks while preserving the completed JSON behavior. Persist safe stage events in the application database, stream them through FastAPI SSE, and let Vue reconnect from the last event ID.

Acceptance checks:

- API and UI run locally against `app.db`; the API schedules document-specific in-process background tasks after persisting intake and logs scheduled/start/completed/failed lifecycle boundaries using safe identifiers only.
- Refresh/reconnect replays ordered events without duplicating terminal state.
- Retry policy is bounded and idempotent; retry-after-failure follows an explicit transition.
- Event/log/exception payload tests prove seeded PII and raw document text cannot escape.
- Stage duration is recorded in model invocation telemetry and safe terminal logs.

### Slice 4 — Interpret email chronology behind the privacy boundary

**Blocked by:** Slices 2 and 3  
**Covers:** US-01, US-03, US-06, US-07

Parse MIME deterministically, deduplicate equivalent bodies, remove contact PII with deterministic parsing and redaction, and use structured semantic extraction for commercial meaning. Presidio remains deferred. The Novara correction must resolve Azimax to EUR 0.134/tablet while preserving 0.128 as superseded evidence.

Acceptance checks:

- Email HTML is never actively rendered; duplicate HTML/plain text does not duplicate lines.
- Adapter-payload tests prove only necessary redacted content is sent and allowed company identity remains.
- Azimax resolves to 0.134 with P.S. provenance and a supersession link to 0.128.
- Malformed structured output retries within a bound and then fails/flags safely.
- Contact/PII is absent from logs, SSE, errors, reports, screenshots, and recorded fixtures.

### Slice 5 — Parse native PDFs with a timeboxed parser gate

**Blocked by:** Slices 2 and 3  
**Covers:** US-01, US-03, US-06, US-07

Use LiteParse as the sole native-PDF parser for Farmaceutica Andina and Mekong. The gate passes if, within the slice timebox, it recovers the source representation, page boundaries, table-like structure, and usable reading order for both PDFs. The application must retain LiteParse output and must not hand-build a universal table parser or treat Markdown as the source of truth.

Acceptance checks:

- Native structure is persisted with page/source coordinates where the chosen parser supplies them.
- Corpus-manifest comparison modes/tolerances—not ad hoc test values—govern expected results.
- Incoterm/place, MOQ/quantity, price basis, discounts/surcharges, storage, and lead time remain distinct.
- Only unresolved redacted sections reach the semantic adapter, asserted from captured test payloads.
- Parse-quality signals are recorded and clean native PDFs avoid OCR.

### Slice 6 — Escalate degraded images/pages to OCR without invented values

**Blocked by:** Slices 3 and 5  
**Covers:** US-01, US-03, US-06, US-07

Add a PaddleOCR/Modal port using the checked-in Piply benchmark reference. Route images and only poor PDF pages to OCR, merge evidence, and prefer null/low-confidence review issues over guesses. Build and test the client/contract now; request user authorization before the live Modal deployment.

Acceptance checks:

- Low-resolution PNG and glare-obscured JPEG take the OCR path; native PDFs do not.
- OCR timeout/service failures retry within policy and end explicitly.
- OCR confidence, page, bounds, and method attach to evidence.
- The glare fixture preserves intentionally unreadable fields as null/low confidence; a mutation inserting a plausible number fails evaluation.
- Modal contract tests run without credentials; after authorized deployment, live smoke and latency measurements against all degraded fixtures are required and labelled separately.

### Slice 7 — Expand the evaluation and operational proof across the corpus

**Blocked by:** Slices 4–6  
**Covers:** US-05, US-06, US-07

Extend the Slice 1 harness to every supplied fixture. Produce field/document metrics, null correctness, source-grounding, correction handling, tier/combination integrity, stage latency, and model cost.

Acceptance checks:

- One deterministic command emits JSON plus a concise Markdown report.
- Special assertions cover all tiers, paired combination strengths, non-overlapping ranges, email correction precedence, glare null correctness, JSONPath/value validation, and unmapped-fact preservation.
- Deterministic parsing/normalization benchmarks have a stable baseline and modest regression budget.

### Slice 8 — Add independent batch progress and failure isolation

**Blocked by:** Slices 3 and 6  
**Covers:** US-01, US-02, US-06

Allow multi-file upload while keeping documents as independent jobs. Aggregate counts from child state without allowing one bad file to block siblings.

Acceptance checks:

- Every file has an independent identity/state; batch state is derived.
- Progress uses the existing SSE boundary and duplicate submission follows an explicit idempotency policy.
- A corrupt file fails while valid siblings complete.

### Slice 9 — Delivery hardening and final narrative

**Blocked by:** The selected submission slices  
**Covers:** all delivered stories

Polish accessibility and operational safety; add CI, visual baselines, complete system docs, README/WRITEUP, and the required agent planning/execution summary.

Acceptance checks:

- CI runs lint, types, unit/integration tests, deterministic evaluation, frontend build, and Playwright smoke tests.
- Visual baselines cover every delivered UI state; logs and artifacts pass the seeded-PII audit.
- README has a reliable evaluator path; WRITEUP explains architecture, cost/latency, privacy, limitations, and production evolution.
- Full validation, running-app exercise, reviews, sweep, and false-confidence audit are evidenced in the final worksheet.

## 4. Dependency and delivery view

```text
1 Schema-learning JSON proof
└── 2 Commercial rules + review
    └── 3 Jobs + SSE
        ├── 4 Email correction
        └── 5 Native PDFs
            └── 6 OCR escalation
                └── 7 Full-corpus evaluation
                    └── 8 Batch

9 Hardening follows the chosen delivery cut.
```

Recommended milestones:

- **Milestone A — Core thesis:** Slice 1 proves source-grounded extraction → validation → selective normalization → human review.
- **Milestone B — Trustworthy product path:** Slices 2–3 add human decisions, provenance, durable work, and live state.
- **Milestone C — Full heterogeneous corpus:** Slices 4–7 add email, native PDF, live Modal OCR, and unified evidence.
- **Milestone D — Full delivery scope:** Slice 8 completes batch processing; Slice 9 completes hardening and submission artifacts.

## 5. Test and evaluation plan

### Per-change gates

- Backend unit tests: domain calculations, state transitions, JSON profiling, source-path validation, selective normalization, and confidence.
- Backend integration tests: SQLite transactions, upload API, API-owned background tasks, SSE replay, review revisions, adapter contracts.
- Frontend component tests: processing states, issue prioritization, evidence/origin badges, correction validation.
- Playwright: upload → progress → review → correct/approve, plus terminal failure.
- Corpus evaluations: all supplied files against versioned ground truth.

### High-value false-confidence checks

- Mutate the pack-price formula and confirm Sanova regression tests fail.
- Make the email parser select the first Azimax price and confirm the correction test fails.
- Point a claimed JSON fact at an invalid path and confirm validation/retry tests fail if it is accepted.
- Replace an unreadable OCR value with a plausible number and confirm null/confidence tests fail.
- Remove event persistence and confirm SSE reconnect/replay tests fail.

### Provider policy

Normal CI must not require network access, model credentials, Modal, or non-deterministic outputs. It uses faithful recorded adapter fixtures and schema validation. After the user authorizes deployment, a separate live integration/evaluation gate exercises Modal OCR and stores safe metrics; the service endpoint is never a CI prerequisite.

## 6. Risks and early decisions

| Risk | Consequence | Mitigation / decision gate |
| --- | --- | --- |
| LiteParse is a young dependency | Output/API churn blocks PDF work | Spike and pin in Slice 6; normalize behind `DocumentParser`; retain replacement option. |
| Presidio false positives remove supplier context | Lower extraction quality | Entity allowlist/policy, redaction audit metadata, corpus tests. |
| SQLite has one writer at a time | API/background-task lock contention | WAL, short transactions, bounded calls, and a concurrency test. |
| LLM output varies | Flaky tests and unsafe records | Structured schema, prompt versioning, deterministic fixtures, bounded retry, human review. |
| Live Modal deployment is not yet authorized | OCR integration cannot be verified against the hosted service | Complete contract/recorded tests first; request authorization only when Slice 6 is ready. |
| Canonical schema grows too quickly | Migration/UI complexity | Version payload, expose a focused review subset, retain rich fields without rendering all initially. |
| Scope expands to every PRD feature | Core thesis remains unfinished | Keep Milestones A–D dependency-ordered, demonstrate each before widening its surface, and document production considerations rather than building them. |

## 7. Definition of done for every slice

- The running app demonstrates the stated behavior end to end.
- Targeted tests fail before/fix the intended behavior and pass afterward.
- `docs/system/test-catalog.md`, architecture, and relevant system docs reflect the change.
- No raw content or PII is added to ordinary logs, snapshots, or model telemetry.
- Research/plan/implementation/wrap-up review findings are resolved or recorded.
- The worksheet contains commands, results, decisions, remaining risks, commit, and worksheet tag.

## 8. Confirmed decisions

- Schema learning is the first runnable slice.
- Deliver the full supplied corpus and batch processing.
- Final OCR integration must use live PaddleOCR on Modal; request deployment authorization when the service/client are ready.
