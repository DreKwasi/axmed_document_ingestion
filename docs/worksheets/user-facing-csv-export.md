# Worksheet: user-facing-csv-export

> Purpose: replace the multi-level internal CSV dump with a terminal-source, product-oriented export.

## Goal and acceptance checks

- Export only terminal processing results, excluding queued and actively processing sources.
- Produce one row per extracted product and one summary row for a terminal source without products.
- Remove internal record type, source ID/status, source-fact, quantity-basis, duplicate currency, presentation, and primary-pack columns.
- Rename source system to file format and retain failure details.
- Add a plain-language extraction confidence explanation from recorded source notes and confidence factors.
- Preserve mapping issue and review information in user-readable aggregate cells.

## Context and constraints

- `pending_review` means extraction is complete but human review is still outstanding, so it is exportable.
- Failed terminal sources remain exportable so `failure_reason` is useful.
- Active ingredients and strengths remain semicolon-delimited lists within one product row.

## Plan

- Define the desired CSV contract in focused unit tests.
- Replace typed sparse rows with terminal-source product rows.
- Exercise the browser download path and inspect the downloaded CSV.
- Update the test catalog, worksheet, and agent feedback; run full validation and review.

## Work log and evidence

- Replaced the prior five-row-kind export (`source`, `product`, `source_fact`, `mapping_issue`, and `review`) with one row per extracted product and a fallback summary row for terminal productless sources.
- Terminal processing statuses are exported; queued and active processing statuses are filtered out. `pending_review` remains exportable because extraction is complete even though human acceptance is not.
- Removed `record_type`, persistence ID/status, raw source-system, source-fact, quantity-basis, line currency, presentation, and primary-pack columns.
- Added `file_format` from the filename extension and `extraction_confidence_explanation` from the API's recorded factor labels/reasons.
- Consolidated active ingredients and strengths with semicolons. Consolidated applicable mapping issue fields and review history onto each product/source row.
- Kept `commercial_currency` as the single currency column, falling back to line pricing currency only when document-level currency is absent.

## Tests, app run, and validation

- Red: `npm test -- --run src/exportCsv.spec.ts` — both contract tests failed against internal headers and missing file format.
- Green: same focused command — 2 tests passed.
- `npm run build` from `frontend/` — type-check and production bundle passed.
- `npx playwright test e2e/review.spec.ts -g "downloads a user-facing product CSV"` — passed against running isolated API/Vite servers; downloaded `axmed-export.csv` and verified its header and product content.
- `bin/agent-validate targeted` — frontend lint, 26 Vitest tests, Ruff, mypy, and 93 backend tests passed.
- `bin/agent-validate full` — frontend lint, 26 Vitest tests, production build, 5 Playwright journeys, Ruff, mypy, 93 backend tests, 5 evaluation tests, and the recorded six-case evaluation run completed successfully.
- `bin/agent-sweep` completed over `HEAD~10..HEAD`; no warning affecting the export change was found.

## Review findings and resolutions

- Research review: no independent provider configured. Systems review identified the old typed sparse rows as an internal persistence representation; quality review required both serializer and browser-download evidence; security review found no new data source or trust boundary.
- Plan review: no independent provider configured. The chosen product-row grain avoids ambiguous rows after removing `record_type`; failed terminal sources retain one summary row so failure context is not discarded.
- Implementation review: quality and code-quality passes found the behavior tests cover filtering, headers, aggregation, and a real download; security found no new data exposure beyond fields already present in the previous export; performance remains linear in documents, products, issues, and reviews.
- Wrap-up review: completion claims match the recorded commands, docs reflect the new contract, and no unresolved product risk was found. Independent-provider review remains unavailable through `bin/agent-review` configuration.

## Docs updated

- Updated the implementation plan, system architecture deep dive, frontend README, test catalog, and agent feedback.

## Handoff / remaining work

- The export deliberately keeps internal-style issue field paths because the user confirmed those fields are useful. Multiple applicable issue/review values are semicolon-delimited within the product row.

## Final commit and tag

- Associated commits will be tagged `worksheet/user-facing-csv-export`.
