# Worksheet: home-source-table

> Purpose: durable handoff trace for the Home source workspace and extraction activity slice.
> Status: implementation complete; validation recorded below.
> Owner: frontend/backend delivery.

## Goal and acceptance checks

- Home is the only primary workspace label; the old product labels are removed.
- Ingest source is available alongside Home and remains usable on narrow screens.
- Uploaded sources render as a source-level table with one combined source column (generated name plus a downloadable file link), confidence, issues, product counts, notes, and status.
- OCR is not exposed as a source status in the UI.
- Opening a source shows normalized product details and a replayable extraction activity timeline.
- PDF and email workers persist preparation, semantic extraction, and normalization events with user-safe messages.

## Context and constraints

The repository already had normalized quotation and field-review persistence. This slice changes the presentation boundary and adds event detail without moving source text or raw provider diagnostics into the browser. Existing dirty worktree changes are unrelated and must remain unstaged.

## Plan

1. Add source summary and serialized event contracts where needed.
2. Add meaningful PDF/email worker event stages and regression coverage.
3. Rework the Vue shell and source list using existing Tailwind utilities; preserve product review actions.
4. Run focused tests, the app, visual checks, and repository validation.

## Work log and evidence

- 2026-09-07: Added `source_name`, extraction confidence, product counts, and notes to document serialization; source naming uses extracted supplier/reference and a humanized filename fallback.
- 2026-09-07: Added `phase`, `message`, and redacted metadata to persisted event serialization. PDF/email workers now persist preparation, semantic identification, and normalization stages before completion.
- 2026-09-07: Replaced the source-card Home view with a responsive source table. The generated source name and original file now share one `Source` column; the file is represented by a compact `Download file` link underneath. The detail view renders an activity timeline from the event API and live SSE payloads.
- 2026-09-07: Added mobile-safe wrapping, compact spacing, and overflow-contained tables; removed the old header/product labels and OCR status text.

## Tests, app run, and validation

- `npm --prefix frontend test -- --run`: passed, 8 tests.
- `npm --prefix frontend run lint`: passed.
- `npm --prefix frontend run build`: passed.
- `cd backend && uv run pytest tests/test_pdf_parser.py tests/test_email_parser.py -q`: passed, 10 tests.
- `bin/agent-validate targeted`: passed after the mypy fix.
- `bin/agent-validate full`: passed — frontend lint, 8 component tests, production build, 2 Playwright journeys, Ruff, mypy, 76 backend tests, and 5 recorded-evaluation tests.
- App smoke checks: `/health`, `/api/v1/documents`, desktop/mobile screenshots, and a 390px viewport overflow check completed; the source table is contained for horizontal touch scrolling on narrow screens.

## Review findings and resolutions

- `bin/agent-review implementation` and `bin/agent-review wrap-up` confirmed that no independent review provider is configured; focused code-quality, UX, app, and validation checks were completed locally.
- A type-check failure from SQLAlchemy's `Sequence` return was fixed by materializing the field-value query as a list.

## Docs updated

- `docs/system/architecture.md`
- `docs/system/test-catalog.md`
- `docs/agent-feedback.md`

## Handoff / remaining work

No product behavior is intentionally left outstanding in this slice.

## Final commit and tag

Commits: `9680428`, `242143f`, `254423d`, `f310b3a`, and the documentation wrap-up commit. Tag: `worksheet/home-source-table`.
