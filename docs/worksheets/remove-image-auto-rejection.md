# Worksheet: image-recovery-confidence-projection

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

Report extraction confidence for every completed image attempt, even when semantic extraction finds zero products. The Home table and backend-owned CSV must both preserve the source-recovery score.

## Context and constraints

- The user reported a glare image whose completed OCR reading showed no extraction confidence.
- Extraction confidence measures OCR/source recovery independently of semantic product yield.
- The user explicitly required the CSV projection to preserve the same score.
- Existing unrelated SQLite-concurrency and frontend-navigation changes were already present and must be preserved.
- The local dev server started successfully on ports 8001/5174, but this command runner ends foreground server processes before a follow-up HTTP probe can connect.

## Plan

1. Add a component regression test for a completed zero-product OCR attempt with recovery confidence.
2. Add API/CSV regression coverage for a zero-product image attempt.
3. Compute attempt confidence after OCR completion independently of line-item count and preserve it in both projections.
4. Run targeted and full validation; record review outcomes.

## Work log and evidence

- 2026-09-09: The attempt serializer passed `has_extracted_result=False` when `line_items` was empty, causing the recovery-confidence policy to return `None` even though OCR had completed.
- 2026-09-09: The UI and CSV briefly added product-count suppression while diagnosing the symptom; the user clarified that this was the inverse of the required behavior, and those suppressors were removed.
- 2026-09-09: Image-attempt serialization now treats the completed OCR stage as sufficient recovery evidence; line-item count does not control extraction confidence.

## Tests, app run, and validation

- Focused: `npm --prefix frontend test -- --run src/App.spec.ts` — 38 passed.
- Focused: `env PYTHONPATH=backend uv run --project backend pytest backend/tests/test_csv_export.py backend/tests/test_confidence.py backend/tests/test_langchain_gemini.py::test_ocr_worker_executes_langchain_when_gemini_configured -q` — 21 passed.
- Targeted validation: `bin/agent-validate targeted` — frontend lint/tests, Ruff, mypy, and 129 backend tests passed.
- Full validation: `bin/agent-validate full` — build, backend tests, and stored evaluations passed. Playwright's five E2E tests could not launch because the local Chromium headless-shell binary is absent.
- App/API: local smoke pending after the corrected projection.

## Review findings and resolutions

- `bin/agent-review research`, `plan`, and `implementation` found no configured independent provider. The corrected domain boundary keeps recovery confidence independent from product yield while leaving mapping confidence and extraction failure separate.

## Docs updated

- `docs/system/test-catalog.md` records completed zero-product image confidence coverage.

## Handoff / remaining work

- Playwright browser installation is an existing environment prerequisite; it was not changed in this session.

## Final commit and tag

- Not committed because the repository had unrelated user changes at session start; this focused change set is left unstaged for review.
