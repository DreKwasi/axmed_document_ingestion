# Task Queue

> Purpose: local, grep-friendly task queue for agents and humans.
> Keep tasks small enough to finish and verify in one worksheet where possible.
> Every task states acceptance checks and the system docs likely to change.
> Do not silently remove completed work: mark it done with a link to its worksheet/commit.
> Autonomous agents select only explicitly marked `ready` tasks.
> Review this queue during session orientation and periodic sweeps.

## Blocked

*None currently blocked.*

## Ready

- [x] **DI-17: Bounded semantic-extraction investigation** — JSON semantic work now begins after durable source persistence, and JSON, PDF, email, OCR-assisted, and direct-vision routes share a LangChain `create_agent` loop with mandatory deterministic validation, changed-feedback investigation, call limits, and no-progress termination. Media routing, safety gates, commercial rules, persistence, confidence, and human decisions remain application-owned. Evidence: `docs/worksheets/di-17-langchain-semantic-agent.md` (kept uncommitted at the user's request).
- [x] **DI-07: Native-PDF semantic fidelity** — v4 makes LiteParse's native parsed representation the source evidence and explicitly rejects a hand-built universal table/Markdown conversion layer. Generic LiteParse context, semantic guidance, and contract normalization now pass both PDF golden cases without supplier-specific rules or invented UOM conversions. Evidence: live run `b23c89eb-dc6a-4dbc-aceb-8e40724f5f43`; failures remain field-level and SQLite-persisted throughout.

## Operational follow-ups

- [ ] **Configure independent review providers** — set `AGENT_REVIEW_COMMAND` and, if desired, `AGENT_FIX_COMMAND` in the developer environment. Docs: agent review, tooling.
- [ ] **Restore Playwright browser runtime** — install the pinned Playwright Chromium browser so `bin/agent-validate full` can execute browser E2E tests. Acceptance: `npm --prefix frontend run test:e2e` runs its five tests rather than failing before launch. Docs: `docs/system/testing.md`. Evidence: `docs/worksheets/semantic-final-candidate-validation.md`.

## Completed

- [x] **DI-01: Schema-learning JSON vertical slice (historical)** — originally delivered versioned mapping confirmation and reuse; migration `20260907_19` later retired that behavior in favor of per-document source-grounded extraction. Evidence: `docs/worksheets/di-01-schema-learning-json.md`, commit `d5c1796`, tag `worksheet/di-01-schema-learning-json`.
- [x] **DI-02: Commercial rules and review decisions** — deterministic calculations, validation, provenance, typed correction revisions, approval/rejection, source access, and multi-document JSON review. Evidence: `docs/worksheets/di-02-commercial-review.md`.
- [x] **DI-03: Durable processing and SSE (historical)** — originally delivered Huey jobs and correction learning; the current system uses API-owned background tasks, one SQLite database, safe persisted events, and reconnectable SSE. Evidence: `docs/worksheets/di-03-durable-learning-sse.md`.
- [x] **DI-04: Email correction extraction** — deterministic MIME intake, redacted semantic job, structured quotation response, and reviewable result. Evidence: `docs/worksheets/di-04-email-chronology.md`.
- [x] **DI-05: Native PDF extraction** — native-text parsing, page quality routing, redacted semantic job, and reviewable result. Evidence: `docs/worksheets/di-05-native-pdf.md`.
- [x] **DI-06: Live Modal OCR escalation** — authenticated Axmed-owned PaddleOCR service, selective page contract, deployed health/auth/fixture checks, and API-to-review smoke. Evidence: `docs/worksheets/di-06-modal-ocr.md`.
- [x] **DI-08: Multi-file processing (historical batch slice)** — originally delivered persisted batch identity; the current endpoint returns independent document records and derives the UI grouping without a batch table while retaining failure isolation. Evidence: `docs/worksheets/di-08-batch-processing.md`.
- [x] **DI-09: Delivery hardening** — CI workflow, Playwright E2E smoke tests, automated PII audit, comprehensive WRITEUP, and docs update. Evidence: `docs/worksheets/di-09-delivery-hardening.md`.
- [x] **DI-10: LangChain + Gemini 3.1 Flash Lite reasoning** — delivered structured semantic output across email, PDF, OCR, and JSON plus price-correction supersession and offline fixtures. Its schema-cache bypass was later retired by migration `20260907_19`; current JSON extraction is per document. Evidence: `docs/worksheets/di-10-langchain-gemini.md`.
