# Worksheet: remove-image-auto-rejection

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

Remove the automatic non-approvable image decision based on OCR/extraction confidence. A low-confidence OCR-assisted or direct-vision attempt with a candidate quotation must remain available through the normal pending-review flow; confidence remains visible as diagnostic evidence.

## Context and constraints

- The user reported a successfully processed glare image shown as `Material unusable` instead of progressing through review.
- Existing unrelated SQLite-concurrency and frontend-navigation changes were already present and must be preserved.
- The local dev server started successfully on ports 8001/5174, but this command runner ends foreground server processes before a follow-up HTTP probe can connect.

## Plan

1. Make the image-pipeline integration test assert review routing for a low-OCR-confidence candidate.
2. Remove the backend auto-rejection branch and its obsolete OCR-quality event handling.
3. Remove obsolete UI/docs descriptions of the threshold and update the test inventory.
4. Run focused, targeted, and full validation; record review outcomes.

## Work log and evidence

- 2026-09-09: Located the policy in `app.documents._apply_confidence_decision`; it called `is_unusable_image_material` and terminally set `auto_rejected` for image confidence below 50 even after both peer attempts ran.

## Tests, app run, and validation

- Pending.

## Review findings and resolutions

- Pending.

## Docs updated

- Pending.

## Handoff / remaining work

- Pending.

## Final commit and tag

- Pending.
