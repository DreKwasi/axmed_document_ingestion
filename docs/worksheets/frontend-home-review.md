# Worksheet: frontend-home-review

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

- Make Home the default page and remove Evaluation Lab navigation/page.
- Present document/source-level review information without a Source column.
- Let a selected document expose supplier-level details and product-level breakdown.
- Show all canonical product/commercial fields in the detail view, including quantity.
- Replace bespoke frontend CSS with Tailwind utilities.
- Identify and regression-test why PDF quantities are missing.

## Context and constraints

- Existing worktree contains unrelated user changes; preserve them.
- UI evidence must include the running app and a deterministic frontend test.
- Backend PDF fixture is `farmaceutica_andina_proforma_FA-COT-2026-118.pdf`.

## Plan

1. Inspect current frontend routes/components and API response shape.
2. Run the app and record the baseline.
3. Reproduce quantity extraction at the parser/model-context seam.
4. Implement the home/detail UI and Tailwind migration.
5. Add focused regression coverage, update docs, run targeted/full validation, and review.

## Work log and evidence

- 2026-09-06: Baseline showed the review table rendered `minimum_order_quantity`; the Andina PDF parser and stored payload contained `quoted_quantity` values.
- 2026-09-06: Added Alembic `20260906_12` and precision follow-up `20260906_13`; workspace migration completed at revision `20260906_13`, backfilling 30 line items from 9 quotations.
- 2026-09-06: Workspace database verification found Andina quantities `6000000`, `1800000`, `2400000`, `120000`, `3000000`, `90000` with UOMs tablet/tablet/tablet/bottle/tablet/bottle.
- 2026-09-06: Replaced Evaluation Lab navigation/page with Home source ledger and source/product detail views using Tailwind utilities.
- 2026-09-06: Normalized line items into `quotation_line_items` plus child tables for INNs, strengths, price tiers, adjustments, and markets; retained `quotations.payload_json` as an immutable extraction snapshot and restored its number formatting at the API boundary.

## Tests, app run, and validation

- `pytest backend/tests/test_migrations.py backend/tests/test_pdf_parser.py backend/tests/test_langchain_gemini.py -q`: 20 passed.
- `npm --prefix frontend test`: 8 passed.
- `npm --prefix frontend run lint`: passed.
- `npm --prefix frontend run build`: passed.
- `npm --prefix frontend run test:e2e`: 2 passed.
- `bin/e2e-server` plus in-app browser screenshot: Home renders with no Evaluation Lab navigation; source list and product detail are reachable through the tested journeys.
- `bin/agent-validate full`: frontend lint/test/build/e2e passed; Ruff, mypy, 75 backend tests, and recorded evaluation command completed. Recorded evaluation summary: 1 passed, 5 not run.

## Review findings and resolutions

- Research/plan review: no independent provider configured; isolated review confirmed the requested Home/source/product hierarchy and quantity seam were covered before implementation.
- Implementation review — behavior/test strength: normalized persistence is written on extraction and review correction, migration backfills existing JSON quotations, and tests cover quantity storage/API exposure, migration backfill, review corrections, and browser journeys.
- Implementation review — code quality: API serialization reads the normalized projection while preserving snapshot formatting; numeric columns use sufficient precision for derived unit prices. Tailwind is the frontend styling entrypoint and the removed page has no browser route/test.
- Security/performance/UX review: no new external permissions or data flows; line-item queries are scoped by quotation and indexed; source-level status is visible before opening the product breakdown. No independent reviewer was available.
- Wrap-up review: validation is green. Remaining risk is that the recorded evaluation runner intentionally skips five cases because their required Gemini/resolver fixtures are unavailable; this is reported by the runner rather than hidden.

## Docs updated

- `docs/system/architecture.md`
- `docs/system/test-catalog.md`
- `frontend/README.md`
- `docs/agent-feedback.md`

## Handoff / remaining work

- Evaluation endpoints remain available server-side for stored evaluation workflows, but the Evaluation Lab UI and browser test were removed per product direction.

## Final commit and tag

Pending final commit/tag. The worktree contained pre-existing changes across the same backend/docs files, so staging must preserve those user-owned changes rather than sweeping the entire worktree into this change.
