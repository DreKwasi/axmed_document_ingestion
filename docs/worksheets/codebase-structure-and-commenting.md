# Worksheet: codebase-structure-and-commenting

> Purpose: establish clear architectural structure, section banners, comprehensive docstrings, and explanatory comments across the full backend and frontend codebase.
> Constraint: preserve 100% of existing behavior, types, database schemas, API contracts, and tests.
> Owner: agent.

## Goal and acceptance checks

- Comprehensive module-level, class-level, and function-level docstrings across all primary backend modules (`app/api.py`, `app/config.py`, `app/database.py`, `app/documents.py`, `app/events.py`, `app/logging.py`, `app/models.py`, `app/security/redaction.py`, and all modules in `app/extraction/`).
- Standardized section headers separating logical concerns in large files (`documents.py`, `api.py`, `json.py`, `llm.py`, `ProductDetailDrawer.vue`, `App.vue`).
- Inline explanatory comments for complex business logic, domain nuances (pharmaceutical pricing, INN, packaging hierarchies, Incoterms, WHO PQ), and extraction algorithms (JSONPath walking, two-pass PDF parsing, OCR quality gating, dual-confidence factorization).
- TypeScript JSDoc comments on `types.ts`, `api.ts`, and `exportCsv.ts`.
- Clean section organization in Vue components (`App.vue`, `ProductDetailDrawer.vue`, `ProductTable.vue`, `SourceTable.vue`, `SourceDetailHeader.vue`).
- Full automated validation (`bin/agent-validate targeted` and `bin/agent-validate full`) passes cleanly (Ruff, Mypy, Pytest, ESLint, Vitest).

## Context and constraints

- Current test suite: 92 pytest backend tests, 22 vitest frontend tests, strict Ruff and ESLint zero-warning rules.
- Existing comments and docstrings must be preserved and expanded, not deleted.
- No functional regressions or altered behavior.

## Plan

1. Create implementation plan artifact and seek user approval.
2. Enrich backend extraction modules (`extraction/json.py`, `extraction/contracts.py`, `extraction/confidence.py`, `extraction/commercial.py`, `extraction/llm.py`, `extraction/pdf_parser.py`, `extraction/pdf_processing.py`, `extraction/image_parser.py`, `extraction/image_processing.py`, `extraction/email_parser.py`, `extraction/email_processing.py`, `extraction/email_reconciliation.py`, `extraction/ocr_client.py`, `extraction/ocr_contract.py`).
3. Enrich backend core modules (`documents.py`, `api.py`, `models.py`, `config.py`, `database.py`, `events.py`, `logging.py`, `security/redaction.py`, `evaluations.py`).
4. Enrich frontend types, API client, CSV export utility, and Vue components (`types.ts`, `api.ts`, `exportCsv.ts`, `App.vue`, `ProductDetailDrawer.vue`, `ProductTable.vue`, `SourceTable.vue`, `SourceDetailHeader.vue`, `ReviewModal.vue`).
5. Run full validation (`bin/agent-validate full`) and record findings.

## Work log and evidence

- 2026-09-08: Initial status verified; baseline `bin/agent-validate targeted` passed cleanly (92 pytest tests, 22 vitest tests, Ruff clean, mypy clean, ESLint clean).
- 2026-09-08: Worksheet initialized.

## Tests, app run, and validation

- To be updated during and after execution.

## Review findings and resolutions

- To be updated during wrap-up.

## Docs updated

- To be updated during wrap-up.

## Handoff / remaining work

- In progress.
