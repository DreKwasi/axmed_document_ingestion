# Worksheet: OCR quality safety gate

> Purpose: record the OCR safety-gate implementation.

## Goal and acceptance checks

- Keep OCR quality as a continuous extraction-confidence input.
- Stop semantic extraction when too little source text is legible.
- Exclude rejected text and pixels from both semantic extraction paths.

## Context and constraints

- Images still expose OCR-assisted and vision results as peer sources when the gate passes.
- No browser or new Playwright test is required.

## Plan

- Add configurable line and document-level thresholds.
- Gate the semantic boundary and mask rejected image regions.
- Add focused regressions, update product/system documentation, and validate.

## Work log and evidence

- Default line floor: 0.80. Default minimum accepted-line ratio: 0.60.
- Below-gate regression verifies that neither semantic extraction call runs and both image attempts fail safely.
- Above-gate regression verifies that vision receives a masked PNG rather than the original image.

## Tests, app run, and validation

- Focused extraction, image-parser, and confidence suites passed (25 tests).
- `bin/agent-validate targeted` passed: ESLint, 16 Vitest tests, Ruff, mypy, and 90 pytest tests.
- Frontend production build passed.
- Stored-fixture probe: low-resolution fax passed the default gate; glare-partial scan failed it.

## Review findings and resolutions

- No independent review provider was configured. Isolated spec pass confirmed that below-gate sources make no model calls and above-gate vision receives masked media. Code-quality pass kept thresholds in typed configuration and source filtering at the semantic boundary.

## Docs updated

- Architecture, PRD, implementation plan, test catalog, and feedback.

## Handoff / remaining work

- Existing already-extracted records are not retroactively failed. Re-extraction applies the new gate.

## Final commit and tag

Not created because the worktree contains pre-existing user changes.
