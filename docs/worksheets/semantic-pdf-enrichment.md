# Worksheet: semantic-pdf-enrichment

## Goal and acceptance checks

- Recover supply and regulatory facts stated in PDF narrative/notes, including scoped shelf life, without weakening table value fidelity.
- Retain the exact layout-aware context for the primary table extraction.
- Use a compact semantic follow-up that only fills missing narrative fields and never overwrites structured facts.

## Context and constraints

- The canonical schema already holds per-line `Supply` (`shelf_life_months`, `minimum_remaining_shelf_life_percent`, storage, cold chain, lead time) and `Regulatory` fields.
- The Andina PDF explicitly states 24 months for items 04/06, 36 months for all other items, and 80% remaining at shipment.
- No supplier-shaped regexes or universal table reconstruction were added.

## Work log and evidence

- Added a deterministic PDF page plan that identifies table-shaped pages while retaining LiteParse geometry for the primary semantic extraction.
- Added a focused LLM semantic-enrichment model keyed by existing line-item source keys. It receives compact, text-only reading order from every page so notes on a table page are not missed, and fills absent supply/regulatory values only.
- Live re-extraction verified exact table quantities/prices are retained and shelf life resolves to 36 months for 01/02/03/05 and 24 months for 04/06; all six lines carry 80% minimum remaining life. Item 06 also carries `FDA/GH/VAR/2026/0442` and its variation-under-review status.

## Tests, app run, and validation

- Targeted PDF parser and LangChain tests passed (17 tests).
- Full validation passed: frontend lint, unit tests, typecheck/build, Playwright E2E (2), backend Ruff, mypy, backend tests (90), and stored evaluations (5). The only output was the pre-existing Starlette `BlockingPortal` deprecation warning and Node's `NO_COLOR`/`FORCE_COLOR` warning.
- A running-app check confirmed the Andina source retains exact table values (for example 6,000,000 tablets at USD 0.0091) and exposes `Shelf life: 36 months (min 80% remaining)` in the product detail.

## Review findings and resolutions

- A trial that removed layout context reduced tokens but corrupted table quantities/prices. It was discarded. Layout context remains in the primary call; only the narrative follow-up is compact.
- Review found that a note can share a page with a table. The compact follow-up now receives text-only reading order from every page, so it retains these notes without repeating layout geometry. No independent review provider is configured; isolated standards/spec/security/UX passes found no remaining issue.

## Docs updated

- Canonical PRD, architecture, and test catalog document the two-pass PDF boundary.

## Handoff / remaining work

- Commit/tag the completed change.
