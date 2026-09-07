# Worksheet: clarify-confidence-and-dosage-labels

## Goal and acceptance checks

- Replace the ambiguous product-drawer term “Independent checks” with a plain-language explanation of same-source consistency checks.
- Standardize the product UI label as “Dosage form” and stop displaying route beside it.

## Context and constraints

- Consistency checks are deterministic comparisons among values in the same source; they are not external verification.
- Route is not a canonical product field; dosage form is the single product-form term.

## Plan

- Update drawer/table copy and add component assertions.
- Correct the PRD example so mapping-path presence is not described as independent validation.

## Work log and evidence

- Replaced the ambiguous label with “Consistency checks” and plain language describing same-source comparison.
- Removed route from the canonical contract, normalized storage, API values, types, and product UI.

## Tests, app run, and validation

- Frontend component coverage is included in `frontend/src/App.spec.ts` and passed in the full validation run.

## Review findings and resolutions

- Use “Consistency checks” because they compare compatible values in the same source; they are not external proof.

## Docs updated

- PRD, context glossary, architecture, and test catalog.

## Handoff / remaining work

- No remaining route compatibility field is retained.

## Final commit and tag

- Implemented by commits `0129cef` and `8c6c11e`.
