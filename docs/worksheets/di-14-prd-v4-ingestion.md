# Worksheet: di-14-prd-v4-ingestion

> Purpose: align implementation with PRD v4's structured/unstructured ingestion split.
> Scope: PRD import, LiteParse representation, PDF semantic handoff, and architecture docs.
> Status: PRD v4 stored; custom Markdown/table reconstruction removed; raw LiteParse JSON now reaches the semantic boundary; both live PDF golden cases pass.
> Source: `/Users/andrewsboateng/Downloads/axmed_document_intelligence_prd_v4.md`.
> Constraint: LiteParse is the sole native-PDF parser; no supplier-specific table rules.
> Constraint: structured JSON mapping and unstructured semantic extraction are separate paths.
> Next: preserve the generic parser/semantic boundary and add future corpus cases; do not reintroduce a universal table parser.

## Goal and acceptance checks

- Repository PRD matches v4's input architecture.
- Structured JSON remains deterministic/schema-memory first.
- PDF, EML, and image inputs retain parser representations and use semantic extraction.
- No application-owned Markdown conversion or universal table parser.
- Focused tests and full validation pass; no commit requested.

## Work log and evidence

- Stored v4 as `docs/product/axmed_document_intelligence_prd.md`.
- Updated architecture and implementation plan to describe the two intake paths.
- Removed the in-progress fixed-column Markdown experiment from the PDF parser.
- Preserved LiteParse page JSON (including page dimensions and any provider layout fields) in redacted artifacts and semantic context.
- Confirmed LiteParse output preserves page text and table-like reading order, while live Gemini cases still report field-level table errors.
- Added generic extraction guidance for `N tablets per pack`, container-only UOMs, and `X mg/5 mL` strengths; contract validation lowercases retained presentation qualifiers and singularizes grammatical UOM plurals.
- Added contract normalization for explicit pack quantities, presentation qualifiers, and base active-moiety names while preserving parenthetical qualifiers in `product.inn`.

## Tests, app run, and validation

- `uv run ruff check app tests`: pass.
- `uv run pytest tests/test_pdf_parser.py tests/test_evaluations.py -q`: 12 passed.
- `bin/agent-validate full`: frontend lint/unit/build/E2E, backend Ruff/mypy/74 tests, and recorded evals: pass.
- `backend/bin/run-evals --live`: run `b23c89eb-dc6a-4dbc-aceb-8e40724f5f43` passed both PDF golden cases; the result and field-level errors are persisted in SQLite.
- `bin/agent-validate full`: frontend lint/unit/build/E2E, backend Ruff/mypy/73 tests, and recorded evals all pass.
- Direct app run: `uv run uvicorn app.api.application:app --host 127.0.0.1 --port 18000`; `/health` and `/api/v1/evaluations` returned successfully.

## Review findings and resolutions

- External review: unavailable because `AGENT_REVIEW_COMMAND` is not configured.
- Isolated review: v4 correctly prohibits application-owned universal table reconstruction; raw LiteParse evidence, generic semantic guidance, and live pass evidence are consistent with the PRD.
- Wrap-up review: external provider still unavailable; isolated check confirms validation evidence is current, live failures are recorded rather than overstated, and no commit was created per user instruction.
- Final isolated review: implementation, tests, SQLite live result, and v4 architecture docs agree; the remaining limitation is lack of a configured independent reviewer CLI.

## Docs updated

- `docs/product/axmed_document_intelligence_prd.md`
- `docs/system/architecture.md`
- `docs/plans/implementation-plan.md`
- `TODOS.md`
- `docs/worksheets/di-05-native-pdf.md`

## Handoff / remaining work

Do not add a generic table parser or Markdown conversion. The raw LiteParse representation is tested and passed to the model, and both current live golden cases pass. Extend coverage with new source documents before changing parser ownership.
