# Worksheet: di-11-dosage-form-normalization

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

Normalize `product.dosage_form` to the core pharmaceutical form (for example, `tablet` or `syrup`), preserving coating, release, and route modifiers in `packaging.presentation`.

## Context and constraints

User requested core forms only and directed that qualifiers live in packaging. No commit or tag until explicitly authorized. The deterministic domain model is the enforcement point so every ingestion source receives the same result.

## Plan

Add a focused model regression test, normalize at the `Product`/`LineItem` boundary, retain qualifiers in `packaging.presentation`, align the model instruction and source-verified golden expectations, then run targeted validation and exercise the running app.

## Work log and evidence

- API health endpoint returned `{"status":"ok","service":"axmed-document-intelligence"}` before the change.
- Current golden fixtures contain modifiers such as `film-coated tablet`, `chewable tablet`, and `pressurised inhalation suspension`.
- User clarified that the preserved qualifier belongs in packaging, not product identity. The final canonical representation is `product.dosage_form: "tablet"` with `packaging.presentation: "film-coated"`.

## Tests, app run, and validation

- Focused regression: `uv run pytest tests/test_langchain_gemini.py::test_product_dosage_form_uses_the_core_pharmaceutical_form` — passed.
- Full validation before the packaging-location refinement: frontend lint, 8 Vitest tests, production build, 3 Playwright tests, Ruff, and 61 backend tests — passed.
- Post-refinement: Ruff, focused regression, model serialization assertion, both golden JSON parses, frontend component test, and production build — passed.
- Browser check: `browser-use open http://127.0.0.1:5173/ && browser-use state` confirmed the running review UI and multiple-file ingest control.

## Review findings and resolutions

- `bin/agent-review implementation` and `wrap-up` found no configured independent provider. Isolated quality, code-quality, security, performance, and UX passes found the qualifier needed to live under packaging; the correction was made before wrap-up.

## Docs updated

- PRD product/packaging contract, test catalog, golden expected outputs, and this worksheet.

## Handoff / remaining work

No commit requested by the user.

## Final commit and tag

Not created by user request.
