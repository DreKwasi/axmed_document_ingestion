# Worksheet: source-detail-review-endpoint

> Purpose: trace and fix the source-detail review endpoint failure after frontend processing.

## Goal and acceptance checks

- Reproduce the error triggered by opening a processed source's detailed view.
- Add a focused regression test at the frontend/API contract seam.
- Fix the smallest underlying contract or routing defect.
- Exercise the application path and pass targeted and full validation.

## Context and constraints

- User reports the failure occurs after initial frontend processing, when the source detail view is clicked.
- Pre-existing unrelated worktree changes are preserved.

## Plan

- Inspect the detail-click request path and backend routes.
- Build a deterministic failing test for the exact request.
- Rank and probe likely causes, then implement the minimal fix.
- Update test inventory and relevant system documentation.

## Work log and evidence

- Traced the image-source row click through `openDocument`, the quotation watcher, and `openImageExtractionForReview`.
- Confirmed the frontend and FastAPI route both use `POST /api/v1/documents/{id}/image-extractions/{approach}/review`.
- Added a one-call assertion to the component test. Before the fix it failed with `expected "spy" to be called once, but got 2 times`.
- Root cause: opening a completed image result called the mutating endpoint directly while the same state change also triggered the quotation watcher. Removed the redundant direct dispatch and retained the watcher so late-arriving extraction attempts still open correctly.
- Added a browser-level request-count regression journey and captured the rendered source detail as Playwright output.

## Tests, app run, and validation

- Red: `npm test -- --run src/App.spec.ts -t "opens the selected image approach directly"` — one failure, observed two calls.
- Green: same focused command — one passed.
- `bin/agent-validate targeted` — frontend lint, 24 Vitest tests, Ruff, mypy, and 93 backend tests passed.
- `npx playwright test e2e/review.spec.ts -g "opening a processed image source"` — one passed against isolated running API/Vite servers; detail rendered and exactly one review request was observed.
- Visual evidence inspected at `frontend/test-results/review-opening-a-processed-158af-e-starts-one-review-request/source-detail.png`; no layout change or visible regression found.
- `bin/agent-validate full` — frontend lint, 24 Vitest tests, production build, 3 Playwright journeys, Ruff, mypy, 93 backend tests, 5 evaluation tests, and the six-case recorded evaluation run completed successfully.
- `bin/agent-sweep` completed over `HEAD~10..HEAD`; no new warning affecting this fix was found.

## Review findings and resolutions

- Research review: no independent provider configured. Isolated systems, security/domain, and quality passes found the mutating endpoint's duplicate invocation was the key contract risk; no authorization or data-boundary change was required.
- Plan review: no independent provider configured. The smallest safe change was to keep one reactive dispatch path and verify both the component seam and running-browser request count.
- Implementation review: quality and code-quality passes found the single-owner mutation path smaller and less race-prone; security, performance, and UX passes found no boundary, loading, or visual change.
- Wrap-up review: claims match the recorded commands and artifacts; docs and regression coverage are synchronized. Independent-provider review remains unavailable by repository configuration.

## Docs updated

- Updated `docs/system/test-catalog.md` with the image-source single-request browser coverage.
- Added an actionable workflow observation to `docs/agent-feedback.md`.

## Handoff / remaining work

- None known. Pre-existing unrelated worktree changes were left untouched.

## Final commit and tag

- Associated fix commit is tagged `worksheet/source-detail-review-endpoint`.
