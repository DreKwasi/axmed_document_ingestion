# Worksheet: supply-and-code-semantics

## Goal and acceptance checks

- Remove the unused `route` field from the canonical product and normalized line-item schema.
- Preserve stated transit/lead time ranges rather than leaving them blank or collapsing them to one invented number.
- Extract and show shipment-level HS customs codes; do not store ATC codes.

## Context and constraints

- The Andina source states `Transit time 26 - 32 days` and `HS CODES 3004.90 / 3004.20 / 3004.10` in shipping details.
- HS codes apply to the shipment/document unless the source explicitly associates one with a product. ATC is out of scope and must not be stored.
- A transit range will be represented as `lead_time_min_days` / `lead_time_max_days`; a singular stated duration remains `lead_time_days`.

## Plan

- Update the canonical contract, semantic prompt, normalized projection, SQLite migration, API types, and detail UI.
- Re-extract an existing source when refreshed values are required, then verify transit range and HS-code display.

## Work log and evidence

- Updated the canonical contract, normalized projection, API types, semantic prompt, and source-detail UI.
- Added Alembic revision `20260907_18`; it preserves lead-time ranges and removes legacy route, HS, and ATC data from projections, snapshots, field values, and evidence records. HS customs codes now live only in `commercial_terms.hs_codes`.

## Tests, app run, and validation

- `env PYTHONPATH=backend uv run --project backend pytest backend/tests/test_migrations.py backend/tests/test_commercial_review.py -q` — 21 passed.
- `npm --prefix frontend test -- --run src/App.spec.ts` — 11 passed.
- Manually started the API and verified a temporary upload returned `204` on delete and `404` on a subsequent retrieval.
- `bin/agent-validate full` completed frontend lint, tests, build, E2E, Ruff, mypy, and backend tests. A final direct backend run reported `92 passed, 1 warning`.

## Review findings and resolutions

- Systems maintainer: retain HS customs codes as a document commercial term rather than projecting an ambiguous shipment code to every product.
- Security/domain: constrain file removal to the upload-directory basename and delete relational dependents before the document to satisfy SQLite foreign keys.
- Quality: cover both the migration cleanup and externally visible delete endpoint.
- `agent-review` has no configured independent provider. The isolated systems, quality, and security passes found no unresolved issue; `agent-sweep` completed without warnings.

## Docs updated

- PRD, context glossary, architecture, and test catalog.

## Handoff / remaining work

- Existing documents retain their previous extraction until explicitly re-extracted; the migration removes retired fields but does not invent newly extracted HS/lead-time values.

## Final commit and tag

- Implemented by commits `0129cef`, `dede987`, and `8c6c11e`.
