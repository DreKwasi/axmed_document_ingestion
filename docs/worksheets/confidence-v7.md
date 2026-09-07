# Worksheet: confidence-v7

> Purpose: record the V7 confidence rewrite and its evidence.

## Goal and acceptance checks

- Confidence evaluates only extracted source facts.
- Commercial availability is separate and can route review without lowering field confidence.
- The UI uses High, Medium, and Low for Confidence; missing fields are Review issues.
- Retain raw numeric evidence for audit and evaluation without presenting it as a percentage.

## Context and constraints

- `/Users/andrewsboateng/Downloads/axmed_document_intelligence_prd_v7.md` is source material. The repository keeps one canonical PRD at `docs/product/axmed_document_intelligence_prd.md`.
- Existing quotations must be reassessed from their stored canonical snapshots, not re-extracted.

## Work log and evidence

- Replaced the old policy that classified absent required values as `Not extracted` confidence.
- Retained the seven commercial review requirements as an availability check: INN, strength, dosage form, currency, quoted price, price UOM, and quoted quantity.
- Low OCR evidence, conflict, ambiguity, poor parser quality, and missing provenance lower Confidence only for a value that exists.
- Added `backend/bin/reassess-confidence` and ran it locally: 2 quotations refreshed with no OCR or model work.
- API now exposes `confidence_band` and `confidence_reason`; raw numeric `confidence` remains audit-only.

## Tests, app run, and validation

- `bin/agent-validate targeted` — frontend lint/Vitest, backend Ruff/mypy, and 82 backend tests passed.
- `cd backend && PYTHONPATH=. uv run python bin/reassess-confidence` — reassessed 2 quotations.
- Local API response confirmed: `3 of 7` available; the image's OCR values are Low while unavailable price/currency/UOM/quantity are distinct review reasons.

## Docs updated

- `docs/product/axmed_document_intelligence_prd.md`
- `docs/system/test-catalog.md`

## Handoff / remaining work

- Full validation passed. No known functional follow-up remains.

## Final commit and tag

- Pending commit; tag after the final commit is created.
