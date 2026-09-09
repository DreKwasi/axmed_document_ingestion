# Worksheet: material-unusable-low-recovery

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

- A completed image reading with zero products and source-recovery confidence below 50% is shown as `Material unusable`, not `Needs review`.
- Future OCR processing persists the same terminal state so it cannot be opened for human quotation review.

## Context and constraints

- The reported Home rows show 46% extraction confidence, zero extracted products, and no mapping issue; mapping quality is irrelevant without material to review.
- Preserve the user's pre-existing uncommitted changes in `frontend/src/App.spec.ts`.

## Plan

1. Add a UI regression that reproduces the reported peer-image row.
2. Route low-recovery image material to the terminal state in the OCR pipeline and prevent a review endpoint from reviving it.
3. Update the system/test documentation, run targeted and full validation, and exercise the UI.

## Work log and evidence

- 2026-09-09: Identified the regression: peer rows inherit their parent `pending_review` status even when `product_count` is zero and their attempt confidence is 46%.
- 2026-09-09: Added the red-capable backend regression. It failed with `pending_review` before the change.
- 2026-09-09: The OCR pipeline now persists `auto_rejected` below 50% source recovery and the review endpoint refuses to promote that terminal material. The frontend also derives the same label for legacy peer rows returned as `pending_review`.

## Tests, app run, and validation

_In progress._

## Review findings and resolutions

_In progress._

## Docs updated

_In progress._

## Handoff / remaining work

_In progress._

## Final commit and tag

_In progress._
