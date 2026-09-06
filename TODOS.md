# Task Queue

> Purpose: local, grep-friendly task queue for agents and humans.
> Keep tasks small enough to finish and verify in one worksheet where possible.
> Every task states acceptance checks and the system docs likely to change.
> Do not silently remove completed work: mark it done with a link to its worksheet/commit.
> Autonomous agents select only explicitly marked `ready` tasks.
> Review this queue during session orientation and periodic sweeps.

## Ready

- [ ] **DI-03: Durable processing and SSE** — add Huey, safe persisted events, reconnectable SSE, bounded retries, diagnostics, and PII-safe execution of queued correction-learning/model-reconciliation jobs. Acceptance: Slice 3.

## Blocked

- [ ] **DI-04: Email correction extraction** — parse the Novara EML, redact before semantic extraction, and preserve price supersession evidence. Blocked by: DI-02, DI-03. Acceptance: Slice 4.
- [ ] **DI-05: Native PDF extraction** — timebox LiteParse behind the parser port, then parse Farmaceutica and Mekong. Blocked by: DI-02, DI-03. Acceptance: Slice 5.
- [ ] **DI-06: Live Modal OCR escalation** — build the secure provider adapter and selective-page OCR path, then request user authorization before deploying to Modal. Blocked by: DI-03, DI-05. Acceptance: Slice 6 and `docs/benchmarks/piply-modal-reference.md`.
- [ ] **DI-07: Corpus evaluation and performance evidence** — report accuracy, null correctness, latency, cost, and schema reuse across all fixtures. Blocked by: DI-04, DI-05, DI-06. Acceptance: Slice 7.
- [ ] **DI-08: Batch processing** — add independent child-document processing with aggregated progress and failure isolation. Blocked by: DI-03, DI-06. Acceptance: Slice 8.
- [ ] **DI-09: Delivery hardening** — CI, visual regression, PII audit, docs, write-up, and full validation. Blocked by: DI-01 through DI-08. Acceptance: Slice 9.

## Operational follow-ups

- [ ] **Configure independent review providers** — set `AGENT_REVIEW_COMMAND` and, if desired, `AGENT_FIX_COMMAND` in the developer environment. Docs: agent review, tooling.

## Completed

- [x] **DI-01: Schema-learning JSON vertical slice** — FastAPI/Vue/SQLite intake, canonical contract, safe JSON validation, versioned recorded mapping, human confirmation, version-scoped trusted reuse, conflict state, migrations, and persisted eval baseline. Evidence: `docs/worksheets/di-01-schema-learning-json.md`, commit `d5c1796`, tag `worksheet/di-01-schema-learning-json`.
- [x] **DI-02: Commercial rules and review decisions** — deterministic calculations, validation, provenance, typed correction revisions, approval/rejection, source access, and multi-document JSON review. Evidence: `docs/worksheets/di-02-commercial-review.md`.
