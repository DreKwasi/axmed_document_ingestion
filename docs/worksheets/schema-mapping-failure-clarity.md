# Worksheet: schema-mapping-failure-clarity

> Purpose: durable handoff trace for one coherent change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.

## Goal and acceptance checks

Make a malformed novel-schema mapping a clear, isolated source failure: the original document retains its metadata and safe reason, and the reviewer sees “Extraction failed” plus that reason rather than a generic “Needs attention”. Accept flat line-item mapping proposals by normalizing them to the canonical mapping contract before application.

## Context and constraints

The live Zenith JSON source produced a proposal with `line_items` source-path entries beside `collection_path`, while the application assumed `line_items.fields`. That raised `KeyError('fields')`; batch isolation then created a second, metadata-less failed receipt. No source-specific mappings or invented field values are permitted.

## Plan

1. Add a failing backend regression for the flat proposal and original-receipt failure behavior.
2. Normalize and validate the generic mapping contract at the mapping boundary.
3. Add a failing UI regression for a safe failed-source explanation, then render it.
4. Run focused, live API, full validation, and review checks.

## Work log and evidence

- 2026-09-07: live API repro: document `d8b6660a…` was `failed` with `Processing failed: 'fields'` and no review reasons. A separate `95c3a1c4…` receipt retained the proposed mapping and source metadata.
- 2026-09-07: research/plan review commands ran; no independent provider is configured. Isolated systems, security, and quality passes will be recorded at wrap-up.

## Tests, app run, and validation

## Review findings and resolutions

## Docs updated

## Handoff / remaining work

## Final commit and tag
