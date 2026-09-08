# Worksheet: failed-mapping-confidence-state

> Purpose: prevent failed extraction results from presenting mapping confidence as pending.

## Goal and acceptance checks

- Reproduce the screenshot state for failed image extraction attempts.
- Display mapping confidence as not applicable when extraction has failed.
- Preserve pending mapping language for genuinely in-progress extraction.
- Add focused regression coverage and verify the rendered table.

## Context and constraints

- Mapping cannot be assessed when no extraction result exists.
- Pre-existing unrelated worktree changes, including staged deletion state, must remain untouched.

## Plan

- Add a component assertion for failed image-attempt rows.
- Centralize the mapping-confidence display label around terminal status.
- Run the focused test, browser path, repository validation, and staged reviews.

## Work log and evidence

- Inspected the supplied screenshot and reproduced two terminal failed image-attempt rows whose Mapping confidence cells showed `Pending`.
- Added a focused component test. Before the fix it failed with `expected 'Pending' to contain 'Not applicable'`.
- Root cause: the mapping label fallback handled a score, a zero-issue assessment, and otherwise always returned `Pending`; it never checked terminal extraction status.
- Added `mappingConfidenceLabel` so failed extraction is `Not applicable`, scored and assessed states retain their existing labels, and only unresolved active work falls back to `Pending`.
- Added a running-browser journey covering both OCR-assisted and Direct vision failed rows.

## Tests, app run, and validation

- Red: `npm test -- --run src/App.spec.ts -t "marks mapping confidence as not applicable"` — failed because the cell contained `Pending`.
- Green: same focused command — one passed.
- `bin/agent-validate targeted` — frontend lint, 25 Vitest tests, Ruff, mypy, and 93 backend tests passed.
- `npx playwright test e2e/review.spec.ts -g "failed image extractions do not show pending"` from `frontend/` — one passed against running isolated API/Vite servers.
- Inspected `frontend/test-results/review-failed-image-extrac-488d6--pending-mapping-confidence/failed-mapping-confidence.png`; both mapping cells visibly read `Not applicable` and the table layout remains intact.
- An earlier root-level `npm --prefix frontend exec playwright ...` invocation failed before application startup because it bypassed `frontend/playwright.config.ts`; rerunning from `frontend/` used the correct harness and passed.
- `bin/agent-validate full` — frontend lint, 25 Vitest tests, production build, 4 Playwright journeys, Ruff, mypy, 93 backend tests, 5 evaluation tests, and the recorded six-case evaluation run completed successfully.
- `bin/agent-sweep` completed over `HEAD~10..HEAD`; no warning affecting this change was found.

## Review findings and resolutions

- Research review: no independent provider configured. Isolated systems, security/domain, and quality passes found this to be a presentation-state defect with no backend or trust-boundary change.
- Plan review: no independent provider configured. The smallest change is a status-aware display helper plus component and browser assertions; pending extraction behavior remains unchanged.
- Implementation review: quality and code-quality passes found the helper explicit and the assertions behavior-facing; security and performance are unaffected, and UX review confirmed the terminal wording matches the extraction state.
- Wrap-up review: recorded commands support the completion claims, docs and tests are synchronized, and no unresolved product risk was found. Independent-provider review remains unavailable by repository configuration.

## Docs updated

- Updated `docs/system/test-catalog.md` and `docs/agent-feedback.md`.

## Handoff / remaining work

- None known. Unrelated worktree and index changes remain out of scope.

## Final commit and tag

- Associated commits will be tagged `worksheet/failed-mapping-confidence-state`.
