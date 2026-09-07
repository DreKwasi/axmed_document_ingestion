# Worksheet: confidence-v8

> Purpose: adopt PRD V8's clarified confidence model in the canonical product requirements, persistence, API, and review UI.

## Goal and acceptance checks

- Confidence is assigned per extracted source field from source evidence, association certainty, and independent validation.
- Signals are not averaged; unresolved conflicts and weak evidence cannot be hidden by unrelated strengths.
- Missing required information is an availability issue, not a low-confidence extraction.
- Derived values have origin/formula/validation status and no extraction-confidence band.
- Existing quotations can be reassessed without rerunning extraction.
- The repository retains one canonical PRD.

## Context and constraints

- Source requirements: `axmed_document_intelligence_prd_v8.md` supplied by the user.
- Canonical requirements: `docs/product/axmed_document_intelligence_prd.md`.
- Preserve unrelated changes in `docs/worksheets/frontend-overhaul.md` and `frontend/index.html`.
- Review fixed point: `cbe4e52`.

## Plan

1. Encode V8 behavior with focused confidence and persistence tests.
2. Replace the former fallback labels with factorized field decisions.
3. Persist derived validation status and expose the explanation in product detail.
4. Migrate, reassess existing records, run the app, and validate the repository.

## Work log and evidence

- Added non-averaged source-evidence, association, and independent-validation decisions.
- Added arithmetic checks for extended and pack prices; a conflict forces Low while corroboration can strengthen otherwise usable evidence.
- Classified every persisted extracted source leaf, while retaining required-field coverage as a separate routing signal.
- Added migration `20260907_16` for normalized-price validation status.
- Reassessed 2 existing quotations successfully.
- Browser verification showed the clean PDF at 42/42 required values with Medium confidence and factorized explanations; the glare image remained in review.

## Tests, app run, and validation

- `uv run pytest tests/test_confidence.py tests/test_commercial_review.py tests/test_commercial_rules.py tests/test_migrations.py -q`: 32 passed.
- `uv run mypy app`: passed.
- `npm test -- --run`: 10 passed.
- `npm run build`: passed.
- Local API restarted on port 8000; `GET /api/v1/documents` verified reassessed field bands and reasons.
- Browser exercised Home → PDF source → product detail and displayed “How confidence was determined”.

## Review findings and resolutions

- During API inspection, non-critical fields still retained the old generic reason. Resolved by classifying every extracted source leaf and adding a regression test.
- No independent review provider was configured. Isolated quality, code-smell, and UX/spec passes found no unresolved issue after the all-field classification fix.
- `git diff --check` passed; derived data is excluded from extraction confidence and migrations preserve its validation state.

## Docs updated

- Canonical PRD confidence section.
- Architecture, implementation plan, and test catalog.

## Handoff / remaining work

- No known remaining work. Existing extraction payloads were reassessed in place; source parsing did not need to be rerun.

## Final commit and tag

- Final commits and `worksheet/confidence-v8` tag created at wrap-up.
