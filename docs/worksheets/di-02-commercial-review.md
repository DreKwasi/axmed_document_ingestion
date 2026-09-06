# Worksheet: DI-02 commercial review

> Purpose: durable handoff trace for deterministic commercial rules and review decisions.
> Scope: preserve quoted commercial values, derive normalized values transparently, validate them, and add correction/approval/rejection commands.
> Status: complete; review-safety core, source retention, typed corrections, and the multi-document JSON table are verified.
> Dependencies: DI-01 is complete at `worksheet/di-01-schema-learning-json`.
> Source requirements: PRD v2 at `docs/product/axmed_document_intelligence_prd.md` and Slice 2 in `docs/plans/implementation-plan.md`.
> Model-learning execution belongs to the PII-safe async path; this slice persists queued correction feedback without pretending to run a live model.
> No Modal deployment is involved.

## Goal and acceptance checks

- Retain source pack price and separately calculate a normalized price using `Decimal` arithmetic.
- Show quoted/derived values, source evidence, validation issues, and review status in the UI.
- Let one ingest action retain every selected source document for independent review.
- Correct, approve, and reject through idempotent commands with stale-revision protection.
- Preserve old evidence and corrections as revisions; extraction success never equals approval.

## Proposed public test seams

- `POST /api/v1/documents/{id}/reviews/correct`, `approve`, and `reject` are the review-decision seam.
- `GET /api/v1/documents/{id}` is the persisted quotation/revision seam.
- The review desk is the user-facing seam for quoted-versus-derived values and decisions.

## Research notes

- DI-01 currently persists one quotation JSON payload and a review-status/revision pair, but exposes no review commands or deterministic price rule module.
- The canonical contract already separates `pack_price`, `quoted_price`, `price_tiers`, `adjustments`, and `normalized_price`; DI-02 will fill those fields without overwriting supplier-provided values.

## Work log and evidence

- 2026-09-06: oriented against the current FastAPI/Vue/SQLite implementation, plan, system docs, and test strategy.

## Tests, app run, and validation

- Red-first API tests initially failed for absent quoted/derived-price rules, absent review commands, and absent validation; the focused suite now passes.
- Browser journey: uploaded a warm Sanova schema into the compact table, verified EUR 3.15/pack stays quoted while EUR 0.035/tablet is displayed as derived, corrected the first row to EUR 4.00/pack, and saw EUR 0.044444…/tablet recalculate at revision 2. Source-path links resolve to the locally stored source file.
- The table accepts multiple selected JSON files. Component coverage asserts all selected files remain visible; the browser automation CLI can select one file at a time, so batch selection is not misreported as a manual browser result.
- PRD v2 was ingested on 2026-09-06. It clarifies that schema resolution uses known mappings, exact canonical fields, a small alias set, fuzzy candidates only, context-aware model resolution, and human confirmation; it explicitly excludes medicine-catalogue RAG. The implementation plan now reflects that order.

## Review findings and resolutions

- Independent review found approval-before-confirmation, approval-with-errors, reversible terminal decisions, stale update, and legacy-migration defects. The current implementation gates decisions on `needs_review` plus `unreviewed`, blocks error-level issues, increments every decision revision, uses a conditional revision/state update, and baselines legacy DI-01 databases at revision `20260906_01` before upgrading.
- Corrections now store before/after audit patches, retain original evidence, append human-corrected evidence, and queue a learning record keyed to the source schema. The later PII-safe worker must run the live model reconciliation and supply that learning context to future extraction; it must never reuse the old commercial value as a new quote.
- The commercial-rule registry now covers date ranges, pack pricing/unit derivation, MOQ values and compatible quoted-quantity/MOQ checks, percentage adjustments, and tier overlap. Each rule declares the issue codes it owns, preventing duplicate execution when new fields are added.
- Review decisions use conditional revision/state updates and replay a duplicate request after an integrity collision. The legacy migration guard now requires an exact known Slice 1 table set before baselining.
- Table actions and final approve/reject controls live in the document table, beside the review status. A real browser run verified a populated Sanova table, preserved quoted values, displayed calculation text, source paths, and the table-contained decision controls.
- Follow-up independent review found the JSON-only format boundary and queued-but-not-executed learning job. Both are intentionally recorded as next-slice work: parser-format ingestion in DI-04/05/06 and PII-safe asynchronous learning execution in DI-03. It also found duplicate rule execution and non-finite correction handling; both were fixed and covered.

## Docs updated

- `docs/system/architecture.md` records the table-contained review flow and strict legacy baseline condition.
- `docs/system/test-catalog.md` records commercial rule seam coverage and the component-review scope.

## Handoff / remaining work

- DI-03 follows with durable processing, Huey, safe persisted events, SSE, and live PII-safe learning reconciliation.

## Final commit and tag

- Validation: `bin/agent-lint --fix`, `bin/agent-validate full`, and `git diff --check` passed. The full suite includes backend API/unit/migration tests, Vue component tests, build/type checks, and isolated Playwright confirmation/correction/approval.
- Wrap-up review: the local review wrapper found no configured external command. Earlier independent review findings were resolved or explicitly sequenced: JSON-only ingestion remains the current format boundary, and live learning execution remains DI-03.
- Pending commit and tag: `worksheet/di-02-commercial-review`.
