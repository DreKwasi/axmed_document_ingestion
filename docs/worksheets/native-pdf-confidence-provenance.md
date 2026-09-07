# Worksheet: native-pdf-confidence-provenance

> Purpose: record the false provenance-issue diagnosis and repair.

## Goal and acceptance checks

- Do not present a clean native PDF's missing leaf locations as per-field extraction failures.
- Keep weak OCR, conflict, ambiguity, and poor parser output as Low-confidence review exceptions.

## Diagnosis and evidence

- The live PDF returned `42/42` available commercial values but only its trade name had persisted evidence.
- Red-capable reproduction: the API reported `No field provenance was recorded` for the recovered quoted price.
- Cause: field confidence treated every clean native-PDF value lacking a leaf evidence record as Low, creating one issue per flattened value.

## Resolution

- Clean native-PDF values without a leaf source location are Medium confidence.
- Only Low-confidence fields generate a confidence review reason; Medium is informative, not an automatic exception.
- Reassessed the two persisted quotations without re-extraction.

## Tests, app run, and validation

- `cd backend && uv run pytest tests/test_confidence.py -q` — 5 passed.
- API regression assertion changed from red to green: recovered quoted price is Medium and the PDF has no review reasons.
- `bin/agent-validate targeted` — 83 backend tests, frontend lint/Vitest, Ruff, and mypy passed.

## Final commit and tag

- Finalized by this documentation commit.
- Tag: `worksheet/native-pdf-confidence-provenance`.
