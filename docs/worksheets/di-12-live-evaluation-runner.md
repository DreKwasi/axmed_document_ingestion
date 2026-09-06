# Worksheet: di-12-live-evaluation-runner

> Purpose: durable handoff trace for the live-PDF evaluation runner hardening.
> Goal: preserve correct SQLite results and summaries as the golden corpus grows.
> Scope: live case selection and persisted summary reporting; no provider call in automated tests.
> Evidence: `backend/tests/test_evaluations.py` with a one-case, mocked-extractor dataset.
> Constraint: no commit or tag until the user explicitly authorizes one.
> Search terms: evaluation, live PDF, golden corpus, SQLite, case count.

## Goal and acceptance checks

The live runner must count the cases it selected from the golden dataset, rather than assuming a fixed corpus size. A test must prove that with a one-case live dataset and persisted result.

## Work log and evidence

- Added the one-case live-PDF runner test. Its first execution exposed the result-to-case foreign-key requirement; the case is now intentionally seeded in the test.
- Its second execution exposed `case_count: 2` in the live summary despite a one-case dataset.
- Replaced the literal with `len(live_cases)` and the regression passed.
- Added `backend/bin/run-evals`: it loads the backend environment, runs evaluation regressions, applies migrations, and persists a recorded SQLite evaluation run. Default mode unsets model credentials after loading the environment, so it cannot call the provider; `--live` is explicit.
- Executed the command successfully: 2 evaluation tests passed and a recorded run persisted with 3 cases, 1 pass, and 2 intentionally `not_run` live-PDF cases.
- Moved golden data, expected outputs, recorded mappings, source documents, and the supplied low-resolution/glare OCR inputs into `backend/evals/`. Dataset fixture paths now resolve relative to the dataset, so the evaluation package is self-contained rather than tied to repository-root paths.
- Added approved OCR evidence cases and `backend/bin/run-evals --ocr`. The command runs the configured PaddleOCR service only, stores provider/model/configuration metadata and anchor recall in SQLite, and never invokes an extraction model. Live evidence: both supplied fixtures passed (2/2).

## Tests, app run, and validation

- Focused: `uv run pytest tests/test_evaluations.py` — 2 passed.
- Full: `bin/agent-validate full` — frontend lint, 8 Vitest tests, production build, 3 Playwright tests, Ruff, 62 backend tests, and `backend/bin/run-evals` all passed.
- Running API: `curl -fsS http://127.0.0.1:8000/health` returned the healthy Axmed service response.

## Review findings and resolutions

- `bin/agent-review implementation` had no independent review provider configured. Isolated quality review confirmed the new test varies corpus size and the script exercises real SQLite persistence; code-quality review found no new complexity; security review confirmed recorded mode removes model credentials; performance/UX are unaffected by the local command.

## Docs updated

- Evaluation-system guide, test catalog, feedback log, and this worksheet.

## Handoff / remaining work

No commit requested by the user.
