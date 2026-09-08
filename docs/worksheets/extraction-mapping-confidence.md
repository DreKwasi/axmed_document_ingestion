# Worksheet: extraction-mapping-confidence

> Purpose: durable handoff trace for one coherent change.
> Created before implementation; records evidence, decisions, validation, and review.

## Goal and acceptance checks

- Replace the source-list `Review issues` column with separate extraction-confidence and mapping-confidence columns.
- Define extraction confidence strictly as source recovery quality, including machine readability, native PDF quality, OCR use/quality, and source cleanliness.
- Define mapping confidence as certainty that extracted values are assigned to the correct canonical schema fields.
- Surface mapping issues at source/product summary level and on the affected product-detail sections and fields.
- Remove the `lowest field bound` concept and its implementation if it has no separate defensible product meaning.
- Update the PRD, implementation/system documentation, tests, and test catalog.

## Context and constraints

- Public test seams: document API confidence/issue payload, source-list columns, and product-detail issue presentation.
- Confidence prioritizes review and never auto-approves a record.
- Existing user changes in the worktree must be preserved.

## Plan

1. Reproduce and trace the current confidence and review-issue behavior.
2. Publish the plan in `docs/plans/implementation-plan.md`.
3. Implement weighted extraction confidence and field-level mapping confidence with transparent reasons.
4. Add failing API/domain and frontend tests, then implement each vertical slice.
5. Run the app, exercise the affected UI, and capture visual evidence.
6. Update product/system docs, run full validation and staged review, then commit and tag.

## Work log and evidence

- Reproduced the misleading `120` review-issues count: it was a sum of field-level confidence reasons, not 120 distinct actionable issues.
- Retired the `lowest field band` aggregation. Added explicit weighted source-recovery confidence and independent canonical mapping confidence with deduplicated mapping issues.
- Updated the source list, product breakdown, and product drawer to use the new API contract.
- Corrected the failed-zero-product case: extraction confidence is now unavailable at the confidence-domain boundary when no assessable extraction result exists, rather than being suppressed by a UI/status conditional.
- Extended product review corrections to every source-backed line-item field across product identity, pricing, quantity/packaging, supply, and regulatory sections. Derived normalized price remains read-only and is recalculated from corrected inputs.
- Added a backend allowlist for those editable line-item paths so the UI cannot persist arbitrary or derived payload fields.
- Removed the unexplained 2% direct-JSON mapping deduction. Exact source-key/canonical matches now score 100%; lower scores require observable provenance weakness, category mismatch, or conflict.
- Simplified product-table mapping issues to a numeric per-line count; detailed issue messages remain routed to their matching product-detail section card.
- Reworked extraction confidence presentation: clean accepted formats no longer receive an automatic format penalty, and the drawer shows a plain-language result with calculation details behind an accessible tooltip.
- Added mapping-confidence tooltips to the source table, product breakdown, and product drawer so users can see the field-score average, contributing reasons, and separate issue count.
- Converted mapping and extraction explanations from hover-only titles into click-toggle popovers so the help affordance works explicitly on desktop and touch interactions.
- Added an explicit help control beside the product-table Mapping confidence heading explaining the field-score average and the observable checks behind it.
- Added amber section-level mapping notes for fields below 100%, so a product score such as 82% identifies the affected product, pricing, quantity/packaging, supply, or regulatory card even when the actionable issue count is zero.
- Replaced internal mapping reason language with reviewer-facing explanations and human-readable field labels (for example, “Country of origin”).
- Added a Home-level CSV export that retains every uploaded source and emits typed source, product, source-fact, mapping-issue, and review rows with shared source metadata and confidence context.

## Tests, app run, and validation

- `npm --prefix frontend run build` — passed.
- `npm --prefix frontend test -- --run src/App.spec.ts` — 12 passed.
- `npm --prefix frontend run build` — passed after the all-fields editor change.
- `npm --prefix frontend test -- --run src/App.spec.ts` — 12 passed after the all-fields editor change.
- `cd backend && uv run pytest tests/test_commercial_review.py -q` — 16 passed after the editable-field registry change.
- `cd backend && uv run pytest tests/test_confidence.py tests/test_commercial_review.py -q` — 22 passed after removing the artificial mapping deduction.
- `npm --prefix frontend run lint` — passed after simplifying mapping issue display.
- `cd backend && uv run pytest tests/test_confidence.py -q` — 7 passed after removing the automatic PDF penalty.
- `npm --prefix frontend test -- --run src/App.spec.ts` — 12 passed after updating the user-facing confidence summary.
- `npm --prefix frontend run build` and `npm --prefix frontend run lint` — passed.
- `npm --prefix frontend test -- --run src/App.spec.ts` — 12 passed with mapping-tooltip assertions.
- `npm --prefix frontend test -- --run src/App.spec.ts`, `npm --prefix frontend run build`, and `npm --prefix frontend run lint` — passed after click-toggle tooltip updates.
- `npm --prefix frontend test -- --run src/App.spec.ts`, `npm --prefix frontend run build`, and `npm --prefix frontend run lint` — passed with the mapping-definition tooltip assertion.
- `npm --prefix frontend test -- --run src/App.spec.ts`, `npm --prefix frontend run build`, and `npm --prefix frontend run lint` — passed after section-level mapping concern placement.
- `cd backend && uv run pytest tests/test_confidence.py -q` — 7 passed with plain-language mapping reasons.
- `npm --prefix frontend test -- --run src/App.spec.ts`, `npm --prefix frontend run build`, and `npm --prefix frontend run lint` — passed after mapping reason updates.
- `npm --prefix frontend test -- --run src/App.spec.ts src/exportCsv.spec.ts` — 14 passed; frontend lint and production build passed with the CSV export.
- `cd backend && uv run pytest tests/test_confidence.py tests/test_commercial_review.py tests/test_json_extraction.py -q` — 26 passed.
- `bin/agent-validate targeted` — frontend lint/tests, backend Ruff, mypy, and 83 backend tests passed.
- Browser/Playwright validation intentionally omitted at user request.

## Review findings and resolutions

- Research and plan review dispatcher reported no independent provider configured. Isolated systems, quality, and trust-boundary passes were used; the key resolution was to separate source recovery from schema assignment and avoid manufacturing an issue per weak field.
- Implementation and wrap-up review dispatchers likewise had no configured independent provider. Final isolated checks confirmed the API payload, source-table columns, section routing, tests, and documentation match the two-confidence model.

## Docs updated

- Product PRD, implementation plan, architecture, and test catalog now describe the two confidence dimensions and retire `Review issues` / `lowest field band`.

## Handoff / remaining work

- Confidence weights are deliberately initial policy values and should be calibrated against a labeled corpus before production automation is contemplated. Human review remains mandatory.
- The shared worktree was already dirty with unrelated in-progress changes, so this session did not create a commit or worksheet tag; staging the full files could capture work outside this change.

## Final commit and tag
