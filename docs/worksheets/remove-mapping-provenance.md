# Worksheet: remove-mapping-provenance

## Goal and acceptance checks

- Remove mapping-path records from the user-facing product drawer and the deterministic mapping evidence stream.
- Retain actual LLM-source and human-correction evidence in durable storage.
- Keep direct structured-source confidence meaningful without treating mapping lineage as proof.

## Context and constraints

- A source path copied into a canonical path is lineage, not evidence that the source states or supports the value.
- `field_evidence` remains an internal audit table for source excerpts/locations supplied by semantic extraction and for human corrections.
- No historical data is deleted in this change.

## Plan

- Stop `apply_mapping` from manufacturing `Evidence` from JSON mapping paths.
- Render no field-evidence/provenance card in the product drawer.
- Classify clean direct JSON without a leaf citation as clear source material but limited association, rather than a review failure.

## Work log and evidence

- Removed automatic `Evidence` creation from deterministic JSON schema mapping. The mapper still transforms data but no longer represents a source-path copy as proof.
- Removed the product-drawer provenance panel. Provenance remains internal for audit/review services.
- A clean direct JSON value without leaf citation remains Medium (clear source, limited field association) rather than becoming a failure solely because mapping lineage is absent.
- Strengthened the semantic prompt: LLM evidence must identify itself as `llm_extraction` and cite a useful source location; `manual` is reserved for a human action.

## Tests, app run, and validation

- Focused checks passed: `uv run ruff check app tests`; `uv run pytest tests/test_canonical_nulls.py tests/test_confidence.py tests/test_langchain_gemini.py -q` (22 passed); frontend Vitest (10 passed), ESLint, and production build.
- Manual running-app check: opened the Andina source and its first product drawer; `Field Evidence & Provenance` was absent.
- Full validation passed: frontend lint, unit tests, build, and Playwright E2E (2); backend Ruff, mypy, full pytest (90), and stored evaluations (5). The only output was the pre-existing Starlette `BlockingPortal` deprecation warning and Node `NO_COLOR`/`FORCE_COLOR` warning.

## Review findings and resolutions

- The user identified the core defect: a mapping path is lineage, not evidence. The implementation removes that conflation.
- Wrap-up review and repository sweep were run. No independent review provider is configured, so isolated standards/spec/security/UX checks were performed against the diff; no remaining issue was found.

## Docs updated

- PRD, architecture, and test catalog distinguish source evidence from mapping lineage.

## Handoff / remaining work

- Existing historical `field_evidence` rows are retained for audit history. A subsequent extraction/persistence refresh replaces the rows from the current canonical snapshot; new deterministic mappings emit no mapping-path records.

## Final commit and tag

- Pending commit and tag.
