# Worksheet: shipping-transit-duration

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks
- **Goal**: Explicitly support and store shipping transit duration in `CommercialTerms`, separating logistics transit duration from manufacturer production lead time.
- **Acceptance checks**:
  1. `CommercialTerms` in `backend/app/extraction/contracts.py` supports `transit_time_days`, `transit_time_min_days`, and `transit_time_max_days`.
  2. LLM extraction prompt instructs Gemini to extract shipment transit duration into `commercial_terms.transit_time_*` while keeping manufacturer lead time on `line_items[].supply.lead_time_*`.
  3. Non-null transit fields flatten dynamically into `quotation_field_values` with review status and confidence audit trail.
  4. Frontend TypeScript types (`frontend/src/types.ts`) include transit duration and payment terms.
  5. Frontend `SourceDetailHeader.vue` displays transit duration (`min–max days` or `N days`) and payment terms under the Delivery Terms card.
  6. Automated unit/integration tests verify backend review sync and frontend rendering.
  7. `bin/agent-validate full` passes completely without regressions.

## Context and constraints
- Manufacturer production lead time (`lead_time_days` in `Supply`) must never be conflated with shipping transit duration.
- Commercial terms are serialized in `QuotationRecord.payload_json` and flattened into `quotation_field_values`, avoiding database schema migrations for quotations.

## Plan
1. Add `transit_time_days`, `transit_time_min_days`, `transit_time_max_days` to `CommercialTerms` in `backend/app/extraction/contracts.py`.
2. Update prompt instructions in `backend/app/extraction/llm.py` to capture transit duration into commercial terms.
3. Update `frontend/src/types.ts` and `SourceDetailHeader.vue` Delivery Terms card.
4. Add backend test in `backend/tests/test_commercial_review.py` and frontend test in `frontend/src/App.spec.ts`.
5. Run targeted and full validation suites; update test catalog and system docs.

## Work log and evidence
- Added transit time integer fields to `CommercialTerms` in `backend/app/extraction/contracts.py`.
- Updated system prompt in `backend/app/extraction/llm.py` with explicit transit extraction rules and 120-char line wrapping.
- Updated `Quotation['commercial_terms']` in `frontend/src/types.ts` with `transit_time_*`, `payment_terms`, and `price_basis`.
- Added computed `transitDuration` to `frontend/src/components/SourceDetailHeader.vue` and rendered it in Delivery Terms.
- Added field labels to `humanizeFieldPath` in `frontend/src/components/ProductDetailDrawer.vue`.
- Added backend test `test_reviewer_can_correct_transit_duration_in_commercial_terms` in `backend/tests/test_commercial_review.py`.
- Added frontend test in `frontend/src/App.spec.ts`.

## Tests, app run, and validation
- `uv run --directory backend pytest tests/test_commercial_review.py`: 17 passed.
- `npm test` in `frontend/`: 23 passed.
- `vue-tsc --noEmit && vite build`: built cleanly with 0 errors.
- `bin/agent-validate targeted`: all passed (frontend lint/vitest, backend ruff/mypy/pytest).
- `bin/agent-validate full`: all passed (frontend lint/vitest/build/playwright, backend ruff/mypy/pytest/run-evals 5 passed).

## Review findings and resolutions
- Initial assertion in `test_commercial_review.py` looked for `review_status == "human_corrected"`; the system stores `review_status == "corrected"` and `extraction_method == "human_corrected"`. Corrected assertion accordingly.
- Ruff line length check caught prompt lines > 120 characters in `llm.py`; refactored lines to wrap cleanly within limit.

## Docs updated
- `docs/system/test-catalog.md`: documented transit duration test coverage.
- `docs/system/system-architecture-deep-dive.md`: updated transit vs lead time architecture section.
- `docs/worksheets/shipping-transit-duration.md`: recorded session details.
- `docs/agent-feedback.md`: logged end-of-session observation.

## Handoff / remaining work
- Complete; ready for user review and commit.
