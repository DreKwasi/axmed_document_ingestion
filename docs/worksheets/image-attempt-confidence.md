# Worksheet: image-attempt-confidence

> Purpose: record the image-attempt source and confidence correction.

## Goal and acceptance checks

- Show OCR-assisted and direct-vision image readings as two source results on Home.
- Penalize extraction confidence when the two readings materially disagree.
- Show an explicit no-issues mapping result instead of a dash.

## Context and constraints

- The user requested code and automated checks only; no browser or Playwright work.
- Existing uncommitted work is preserved and this session will not commit unrelated changes.

## Plan

- Add red-capable confidence and UI regressions.
- Serialize confidence per image attempt and project attempts into source rows.
- Run focused suites, targeted validation, and an application build/start check.

## Work log and evidence

- Stored glare run: OCR-assisted recovered 1 product, vision-direct recovered 6; OCR confidence averaged 60.4%.
- Stored low-resolution run: both approaches recovered 6 products; OCR confidence averaged 98.1%.

## Tests, app run, and validation

Pending.

## Review findings and resolutions

Pending.

## Docs updated

Pending.

## Handoff / remaining work

Pending.

## Final commit and tag

Not created because the worktree already contains user changes.
