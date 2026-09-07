# Supplier Document Intelligence — Implementation Plan

> Purpose: turn the Axmed document-intelligence PRD into an executable, take-home-sized delivery plan.
> Status: approved for full scope; publish dependency-ordered work into `TODOS.md` before implementation.
> Strategy: ship tracer-bullet vertical slices, each demoable through the running FastAPI and Vue application.
> Critical thesis: deterministic extraction and remembered mappings handle known structure; AI handles novelty and ambiguity.
> Trust boundary: the system may auto-accept only clean high-reliability records; human approval is recorded only when a person reviews. Missing or unreadable values remain explicit.
> Source: `docs/product/axmed_document_intelligence_prd.md` and the checked-in synthetic corpus in `sample_documents/`.

## 1. Outcome and scope

The finished take-home should demonstrate one coherent workflow:

1. Upload one or more supplier documents.
2. Observe durable processing progress.
3. Receive a canonical quotation with original commercial meaning intact.
4. See derived values, uncertainty, validation issues, and source evidence separately.
5. Route exceptions to review, then correct, approve, or reject the result with an auditable outcome.
6. Re-upload a known supplier schema and demonstrate less model work, lower latency, and lower cost.

### Required product stories

- **US-01 — Ingest:** A procurement user can upload JSON, EML, PDF, PNG, or JPEG supplier documents and receive an explicit accepted/rejected result.
- **US-02 — Track:** A user can see each document move through processing stages and can reconnect without losing work.
- **US-03 — Review:** A reviewer can inspect canonical quotation lines, prioritized uncertainty, source-versus-derived values, and evidence.
- **US-04 — Decide:** A reviewer can correct fields and approve or reject a quotation; accepted state is never inferred from extraction success.
- **US-05 — Learn:** A reviewer-confirmed supplier mapping can be reused deterministically when the same schema fingerprint appears again.
- **US-06 — Operate:** An engineer can diagnose failures and compare parse, OCR, PII, model, and total latency without raw document text in logs.
- **US-07 — Evaluate:** An evaluator can run the supplied corpus against checked-in ground truth and inspect field-level accuracy and cost.

### Deliberate cut line

The delivery scope includes every supplied format (JSON, email, native PDF, and degraded images), live PaddleOCR on Modal, batch upload, corpus evaluation, and final documentation. The take-home does not build production RBAC, distributed storage/queues, enterprise audit retention, or broad multilingual support; it documents their production implications instead. Deployment itself remains a user-authorized action when Slice 6 is ready.

## 2. Proposed technical baseline

### Repository and runtime

- Monorepo with `backend/` (including `backend/evals/`), `frontend/`, `sample_documents/`, and `data/` (ignored runtime state).
- Python 3.12 managed by `uv`; FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, Huey/`SqliteHuey`, pytest, Ruff, and mypy.
- Vue 3, Vite, and TypeScript with Vitest, Vue Testing Library, and Playwright.
- `app.db` for application state and `tasks.db` for Huey. Enable WAL and keep worker writes short.
- One documented command starts API, worker, and frontend; one command runs the full validation suite.

Python 3.12 is a useful compatibility target because current Presidio guidance supports it. LiteParse is recent and should sit behind a parser adapter with a one-slice feasibility gate. `SqliteHuey` remains appropriate for the local worker boundary and keeps queue state separate from application state.

### Backend boundaries

Keep orchestration independent of vendors through small ports:

```text
DocumentPipeline
├── StructuredIngest     JSON schema recognition + trusted mapping memory
├── UnstructuredParsers  MIME | LiteParse | PaddleOCR
├── ParseQualityPolicy   native text/table quality and OCR decision
├── OcrClient            Modal PaddleOCR | fixture fake
├── PiiRedactor          Presidio
├── SemanticExtractor    LangChain structured output | fixture fake
├── SchemaMappingStore   fingerprinted mappings and trust counters
├── QuotationRules       normalization, calculations, validation, confidence
└── ReviewService        correction, approval, rejection, mapping confirmation
```

The pipeline owns stage transitions; adapters do not mutate review state directly.

### Persistence model

Use relational tables for operational state and versioned JSON for the evolving canonical payload:

- `documents`: identity, file metadata, type, status, failure reason, batch ID.
- `document_artifacts`: native parse, OCR parse, and redacted model input with storage references and quality metadata.
- `quotations`: canonical payload, schema version, current review status, revision.
- `field_evidence`: JSON-pointer field path, source location/page/bounds/snippet, method, confidence, supersession link.
- `processing_events`: monotonic ID, document ID, stage, safe metadata, timestamp; source for SSE.
- `reviews`: action, field patches, reviewer note, prior/new revision, timestamp.
- `schema_mappings`: supplier/source system/fingerprint/path mapping plus trust counters and human verification.
- `model_invocations`: operation, model, prompt/schema version, token counts, duration, estimated cost; never raw sensitive input.
- `batches`: aggregate identity and progress only.

Keep business values readable in the canonical payload. Store provenance separately by field path rather than wrapping every scalar. Derived values still carry their calculation and `derived: true` marker in the payload.

### Canonical contract and ground truth

Version the canonical Pydantic model before the first parser. Its MVP must include quotation type/reference/dates, supplier, currency and commercial terms, line items, product identity with paired ingredient strengths, original packaging description, quoted quantity versus MOQ, quoted price and basis, price tiers/adjustments, normalized price, supply details, regulatory fields, and source metadata. The first UI may show a subset, but parsers must not silently discard supported values.

Unknown means `null` plus a review issue when the field matters; it never means an empty string, zero, or model guess. Use `Decimal` for money and explicit units. Stored quotations and mappings carry schema/transformation versions; incompatible versions require migration or re-evaluation.

Check in a corpus manifest from Slice 1. For each fixture it names the document class, expected fields, intentionally unreadable/unknown fields, expected review issues, and comparison mode: exact, normalized text, decimal tolerance, ordered/unordered collection, or null correctness.

### Schema-mapping contract

A mapping lookup key is `(supplier/source_system, optional source schema version, normalized-path fingerprint)`. A mapping entry records source path pattern, canonical field, transformation/version, provenance, trust state, `times_seen`, `times_confirmed`, `human_verified`, and conflicts.

- Same shape with different values is a cache hit; the same supplier with a changed normalized shape is a miss.
- A trusted hit is forbidden from calling the semantic schema-mapping adapter.
- Confirming a proposed mapping makes that mapping reusable.
- A small global alias layer handles only obvious universal names. Exact canonical matches precede aliases.
- Fuzzy matching is candidate generation only; it never accepts a mapping. The semantic resolver receives candidates plus field/sample/nearby-field/schema context and may still return an uncertainty flag.
- Correcting a wrongly mapped field updates or revokes only the affected mapping and records an audit event. It stores a field-interpretation lesson, never a historical commercial value to copy into later offers.
- A warm run must match the approved cold-run canonical payload except for identifiers, timestamps, and operational metrics.

This project does not build a medicine-catalogue RAG layer. Its retrieval-like memory is the supplier/schema mapping store.

### State and trust model

Keep processing, system routing, and human outcomes separate:

```text
processing:      received → parsed → queued → processing → terminal | failed
system decision: auto_accepted | needs_review
human outcome:   unreviewed → approved | corrected | rejected
```

The system decision is made after extraction from critical-field coverage, observable field reliability, deterministic validation, conflicts, and OCR/parser warnings; it is not a model-confidence average. The default review queue contains only `needs_review` + `unreviewed` exceptions, while `auto_accepted` records remain visible in the source list. Approval requires no note. A correction is a terminal, audited human outcome with before/after patches. Rejection requires one structured reason (`unreadable_source`, `incorrect_extraction`, `unsupported_document`, `duplicate`, `not_a_quotation`, or `other`) and may include a note. Commands are idempotent by request key and stale revisions conflict.

### Local data and privacy boundary

Classify data before implementation:

- Raw documents and unredacted snippets: local restricted source/evidence path only.
- Redacted model input: persisted only when needed for debugging/evaluation and never mixed with raw artifacts.
- Canonical commercial records: reviewer-visible; may retain supplier/company identity.
- Events, logs, exceptions, telemetry, fixtures, screenshots, and reports: safe metadata only; no raw text, personal email/phone/name, banking/account identifiers, or unrelated addresses.

Validate media signatures as well as extensions, impose upload/page/text limits, generate safe storage names, contain parser failures, and never render active email HTML. Seeded-PII tests must cover model payloads, logs, SSE, exceptions, reports, and recorded fixtures while proving allowed company identity remains.

## 3. Vertical implementation slices

### Slice 1 — Prove schema learning in one runnable JSON path

**Blocked by:** None  
**Covers:** US-01, US-03, US-05, US-07

Build the walking skeleton and the product’s core thesis together: FastAPI, minimal Vue review screen, SQLite migrations, versioned canonical contract, corpus manifest, safe upload, path normalization/fingerprinting, a recorded semantic mapping adapter, human mapping confirmation, and trusted reuse. Use Sanova as the unfamiliar JSON fixture.

Acceptance checks:

- A fresh checkout installs, migrates, and starts the backend/frontend with one documented command.
- First upload produces a proposed mapping and canonical result; a reviewer can confirm the mapping in the UI.
- Re-uploading identical-shape data with changed values is a trusted hit, produces the same approved shape, and the adapter boundary asserts zero schema-mapping calls/tokens/cost.
- Renaming one normalized source path creates a miss; an ambiguous/conflicting mapping requires review.
- The cold/warm report records mapping calls, recorded token/cost metadata, and same-machine pipeline latency, clearly labelled fixture-backed.
- Media signature/size/name protections, canonical null semantics, and the Sanova manifest are tested.

### Slice 2 — Add deterministic commercial rules, evidence, and review decisions

**Blocked by:** Slice 1  
**Covers:** US-03, US-04, US-07

Complete the Sanova quotation path with price normalization, validation, field evidence, confidence/issues, correction revisions, approval, and rejection. Retain the supplier’s pack price while deriving unit price with `Decimal` arithmetic. This slice supports multiple selected JSON documents; the PRD's EML/PDF/image router arrives with their parser slices.

Acceptance checks:

- Review UI separates quoted and derived price, shows formula/source path, and prioritizes failed validations.
- Corrections retain prior evidence, enqueue PII-safe learning feedback about field interpretation (never a reusable historical price), update/revoke an affected mapping where applicable, and remain unapproved until an explicit approval.
- Approve/reject/correct commands are idempotent; stale revisions conflict; failed or stale records cannot be accepted downstream.
- Tests cover arithmetic, quantities versus MOQ, invalid dates/percentages/tiers, mapping correction, and review transitions.
- One ingest action accepts multiple documents and preserves independent review state/source access for each; a Playwright test uploads, confirms mapping, corrects a field, and approves the current revision.

### Slice 3 — Add durable jobs and reconnectable live progress

**Blocked by:** Slice 2  
**Covers:** US-02, US-06

Move unpredictable processing behind Huey while preserving the completed JSON behavior. Persist safe stage events in the application database, stream them through FastAPI SSE, and let Vue reconnect from the last event ID.

Acceptance checks:

- API, worker, and UI run separately against `app.db` and `tasks.db`.
- Refresh/reconnect replays ordered events without duplicating terminal state.
- Retry policy is bounded and idempotent; retry-after-failure follows an explicit transition.
- Event/log/exception payload tests prove seeded PII and raw document text cannot escape.
- Stage duration is recorded and exposed in a safe local diagnostics view/report.
- Queued human-correction learning is consumed only after PII redaction. The worker invokes the semantic resolver with correction interpretation and mapping evidence, persists its outcome, and the next matching schema run receives that preference as non-authoritative context.

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

Extend the Slice 1 harness to every supplied fixture. Produce field/document metrics, null correctness, correction handling, tier/combination integrity, schema reuse, stage latency, and model cost.

Acceptance checks:

- One deterministic command emits JSON plus a concise Markdown report.
- Special assertions cover all tiers, paired combination strengths, non-overlapping ranges, email correction precedence, glare null correctness, and warm-schema call prohibition.
- Cold/warm timing uses a documented same-machine method; simulated/recorded and live provider measurements are separate.
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

- **Milestone A — Core thesis:** Slice 1 proves unknown → confirmed → deterministic warm-schema reuse.
- **Milestone B — Trustworthy product path:** Slices 2–3 add human decisions, provenance, durable work, and live state.
- **Milestone C — Full heterogeneous corpus:** Slices 4–7 add email, native PDF, live Modal OCR, and unified evidence.
- **Milestone D — Full delivery scope:** Slice 8 completes batch processing; Slice 9 completes hardening and submission artifacts.

## 5. Test and evaluation plan

### Per-change gates

- Backend unit tests: domain calculations, state transitions, key normalization, fingerprinting, mappings, validation, confidence.
- Backend integration tests: SQLite transactions, upload API, Huey jobs, SSE replay, review revisions, adapter contracts.
- Frontend component tests: processing states, issue prioritization, evidence/origin badges, correction validation.
- Playwright: upload → progress → review → correct/approve, plus terminal failure.
- Corpus evaluations: all supplied files against versioned ground truth.

### High-value false-confidence checks

- Mutate the pack-price formula and confirm Sanova regression tests fail.
- Make the email parser select the first Azimax price and confirm the correction test fails.
- Disable fingerprint changes and confirm schema-drift tests fail.
- Replace an unreadable OCR value with a plausible number and confirm null/confidence tests fail.
- Remove event persistence and confirm SSE reconnect/replay tests fail.

### Provider policy

Normal CI must not require network access, model credentials, Modal, or non-deterministic outputs. It uses faithful recorded adapter fixtures and schema validation. After the user authorizes deployment, a separate live integration/evaluation gate exercises Modal OCR and stores safe metrics; the service endpoint is never a CI prerequisite.

## 6. Risks and early decisions

| Risk | Consequence | Mitigation / decision gate |
| --- | --- | --- |
| LiteParse is a young dependency | Output/API churn blocks PDF work | Spike and pin in Slice 6; normalize behind `DocumentParser`; retain replacement option. |
| Presidio false positives remove supplier context | Lower extraction quality | Entity allowlist/policy, redaction audit metadata, corpus tests. |
| SQLite has one writer at a time | Worker/API lock contention | Separate Huey DB, WAL, short transactions, bounded retry, concurrency test. |
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
