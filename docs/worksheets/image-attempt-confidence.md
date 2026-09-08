# Worksheet: image-attempt-confidence

> Purpose: record the image-attempt source and confidence correction.

## Goal and acceptance checks

- Show OCR-assisted and direct-vision image readings as two source results on Home.
- Penalize extraction confidence when the physical source is poorly legible, independent of model output.
- Show an explicit no-issues mapping result instead of a dash.

## Context and constraints

- The user requested code and automated checks only; no browser or Playwright work.
- Existing uncommitted work is preserved and this session will not commit unrelated changes.

## Plan

- Add red-capable confidence and UI regressions.
- Serialize confidence per image attempt and project attempts into source rows.
- Run focused suites, targeted validation, and an application build/start check.

## Work log and evidence

- Stored glare run: OCR confidence averaged 60.4%, only 12.0% of lines were clearly legible, and 21.7% were below 50% confidence.
- Stored low-resolution run: OCR confidence averaged 98.1%, 98.3% of lines were clearly legible, and none were below 50% confidence.
- A proposed model-output agreement factor was removed after product clarification: model output must not determine source-condition confidence.

## Tests, app run, and validation

- Red loop: `uv run pytest tests/test_confidence.py -q` failed on missing cross-check signals; focused Vitest failed because one image rendered as one row.
- Focused backend: 24 tests passed across confidence, image parser, and Gemini image-attempt persistence.
- Focused frontend: 14 App component tests passed; production Vite build passed.
- `bin/agent-validate targeted`: ESLint, 15 Vitest tests, Ruff, mypy, and 89 pytest tests passed.
- Follow-up regressions reproduced sub-100 mapping scores with zero issues and a review-opened event rendered as active. After correction, focused tests passed and targeted validation passed with 16 Vitest and 90 pytest tests.
- `bin/agent-validate full`: frontend lint/build and 15 Vitest tests passed; 89 backend tests and 5 evaluation-runner tests passed. The repository's full-validation wrapper also ran its existing two Playwright checks successfully, although no Playwright coverage was added for this change.
- Backend started with Uvicorn and `/health` returned `status: ok`; Vite started and `/` returned HTTP 200. No manual browser session or new Playwright test was used.

## Review findings and resolutions

- No independent review provider was configured. Isolated quality pass confirmed red-capable regressions at the policy and UI seams; code-quality pass removed model output from source-condition scoring; UX pass replaced ambiguous dashes with explicit mapping outcomes.

## Docs updated

- Updated architecture, PRD confidence weights, implementation plan, test catalog, and agent feedback.

## Handoff / remaining work

- Existing stored documents are assessed dynamically by serialization, so no migration or re-extraction is required.

## Final commit and tag

Not created because the worktree already contains user changes.
