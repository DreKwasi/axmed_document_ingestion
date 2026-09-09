# Worksheet: orchestrated-structured-extraction

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/orchestrated-structured-extraction` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

- [x] Identify root cause of the 75-second silent stalls and `ValueError: Semantic extraction agent ended without a valid structured candidate` failures.
- [x] Replace the unguided multi-tool loop with application-controlled orchestration:
  - Evidence-free primary extraction with narrative.
  - Separate full grounding against the exact populated canonical fields.
  - Deterministic claim validation before evidence is attached.
  - A bounded `while` loop that investigates all remaining ungrounded fields together.
- [x] Add clear operational logging showing extraction duration, line item counts, and validation results.
- [x] Update system documentation (`architecture.md`), feedback log (`agent-feedback.md`), and worksheets.
- [x] Pass 100% of targeted validations (`bin/agent-validate targeted`).

## Context and constraints

- The repository previously attempted an open-ended autonomous agent loop using LangChain's `create_agent` with tools (`search_evidence`, `inspect_evidence`, `validate_candidate`) and `ToolStrategy(SemanticCandidate)`.
- Without an orchestrator directing the stages, the model entered a repetitive tool-calling loop (calling `validate_candidate`, receiving validation output, re-querying evidence, and re-validating) without ever calling the output schema tool to conclude.
- On the 10th model turn, `ModelCallLimitMiddleware` triggered its hard limit (`exit_behavior="end"`), aborting the agent graph with `structured_response = None`, crashing the background extraction worker.
- All code changes must comply with repository conventions (Ruff line length <= 120, Mypy strict typing).

## Plan

1. Analyze background task logs and trace model execution during document extraction.
2. Implement `run_semantic_extraction` in `backend/app/extraction/semantic.py` as direct structured model calls selected by Python.
3. Validate extraction structure/commercial rules, then validate grounding claims against canonical fields and source references/values.
4. Keep unresolved evidence fields in one list and pass that complete list through a maximum of three investigation runs.
5. Test the semantic and source-processing seams.
6. Update `docs/system/architecture.md` and `docs/agent-feedback.md`.
7. Run targeted validation.

## Work log and evidence

- Task inspection revealed 10 consecutive model calls to Gemini 3.5 Flash Lite over 74 seconds with zero terminal feedback.
- Replaced `run_semantic_investigation` with application-controlled `run_semantic_extraction`.
- Validated on live PDF `farmaceutica_andina_proforma_FA-COT-2026-118.pdf` (ID `78b9e93e`):
  - Extracted 6 line items, supplier `Farmaceutica Andina S.A.S.`, Incoterms `FOB Cartagena`, and payment terms `T/T 30 days` in 12.87 seconds.
  - Deterministic validation executed in 3ms, detecting 1 date-range issue (`invalid_date_range`) routed to human review.
  - Document status transitioned to `pending_review`, extraction status to `completed`.

## Tests, app run, and validation

- `bin/agent-validate targeted`:
  - Frontend ESLint: 0 warnings
  - Frontend Vitest: 32/32 tests passed (214ms)
  - Backend Ruff: All checks passed!
  - Backend Mypy: Success (0 issues across 29 source files)
  - Backend Pytest: 124/124 tests passed (7.00s)

## Review findings and resolutions

- Root cause: An unguided LLM with a grab bag of tools lacks the stateful logic to know when and how to exit, especially when validation tools return instructions to keep investigating.
- Resolution: The application orchestrates the pipeline stages: Parse -> Structured Extraction -> Deterministic Validation -> Event/Queue Dispatch.

## Docs updated

- `docs/system/architecture.md`: Updated semantic extraction section to document application-orchestrated structured extraction pipeline.
- `docs/agent-feedback.md`: Added entry on orchestrated semantic extraction vs unguided tool loop.
- `docs/worksheets/orchestrated-structured-extraction.md`: Created this worksheet.

## Handoff / remaining work

- The direct-only orchestration described above was superseded on 2026-09-09 by an application-controlled flow: primary structured extraction -> deterministic extraction validation -> full grounding -> deterministic claim validation -> bounded evidence-only investigation -> deterministic revalidation.
- The application stops after three investigation runs as a resource-safety boundary. A failed or incomplete grounding call enters that same bounded path and retains the primary candidate.
- Focused checks completed after the replacement: semantic-agent, LangChain integration, and settings tests (17 passed); Ruff and Mypy passed for the touched backend modules.
- No commit was created, per user instruction.

## 2026-09-09 — Google-only provider

- Removed OpenRouter configuration, provider construction, fallback-model iteration, tests, environment example, and the `langchain-openrouter` dependency.
- Direct Google Gemini `gemini-3.5-flash-lite` is the sole code-owned semantic provider. A Gemini failure is surfaced and does not switch to another provider.
- Focused Ruff, Mypy, and semantic/provider tests passed; full validation is recorded after wrap-up.
- `bin/agent-validate targeted` passed after the change: frontend lint/Vitest (33 tests), backend Ruff/Mypy, and backend pytest (118 tests). FastAPI startup and `GET /health` also passed.
- `bin/agent-review wrap-up` found no configured independent provider. Isolated review found no remaining executable alternate provider, fallback iteration, OpenRouter dependency, or provider-policy documentation mismatch.
- No commit was created, per user instruction.

## 2026-09-09 — Mapping issue disclosure cleanup

- Removed the duplicated "fields below full mapping confidence" block from each product-detail section. The existing expandable mapping-issue row with “View details” remains the sole details view.
- Removed the related unused tooltip state/helpers and added a component regression assertion.
- Frontend ESLint and Vitest passed (33 tests). Browser tests were not run per user instruction.
- No commit was created, per user instruction.

## 2026-09-09 — Investigation no-progress and evidence export

- Confirmed from the live Sanova record that 25 semantic fields were ungrounded, while the confidence layer inflated the persisted count to 76 by treating 48 valid but sub-100 mappings and three derived quoted prices as issues.
- Mapping issues now represent missing or contradictory grounding, not every grounded field below 100%. Mapping confidence remains independent and can still be below 100%.
- Quoted prices derived from pack prices inherit the pack-price source evidence, preventing three post-normalization provenance gaps.
- The investigation loop stops after one zero-claim response with `no_progress`; rejected claims can still feed another bounded correction attempt.
- The JSON investigation prompt explicitly distinguishes raw JSON source values from normalized canonical values and permits `semantic_json` grounding.
- CSV export now includes evidence canonical fields, source paths, source locations, extraction methods, and superseded paths.
- Focused backend tests passed (31). Full validation is recorded at wrap-up. No commit was created.

## 2026-09-09 — Confidence routing update

- Added deterministic policy routing: `pre_approved` requires 100% extraction confidence, 100% mapping confidence, and zero mapping issues. Any other usable source remains reviewable.
- Removed the OCR hard rejection gate. Low-legibility images now run OCR-assisted and direct-vision extraction, retain their evidence for inspection, and become non-approvable `auto_rejected` material when source recovery scores below 50.
- Clarified the mapping issue wording: “confirm amount” now means an independent cross-check was unavailable; it does not ask the user to re-enter an amount.
- Confirmed JSON has no persisted mapping/profile cache. Source deletion already removes the stored upload and all document-scoped derived records.
- Evidence: application health endpoint passed; `bin/agent-validate targeted` passed (116 backend tests, frontend lint/Vitest, Ruff, and Mypy).

## 2026-09-09 — Mapping-confidence coverage

- A quotation without any source-linked evidence previously returned a null mapping score and appeared as “No issues” in the source table. It now receives a visible 0%/Low score and a `missing_mapping_evidence` issue; only a source with no quotation remains not applicable.

## 2026-09-09 — Field-level provenance repair

- Missing evidence is now assessed for every populated canonical field, not silently omitted from the mapping average. PDF, email, and image semantic requests require addressable page/body/OCR evidence; missing evidence is returned to the bounded investigation model as a targeted issue.

## 2026-09-09 — Frontend confidence presentation audit

- Removed internal document notes from source-list rows. Source-list and product mapping confidence now render `—` when unavailable instead of implying “No issues”.
- The frontend no longer derives `pre_approved` from a mapping shortcut or substitutes a document score for a product score; only the backend decision and field-level evidence determine those displays.
- Removed persisted content hashes for every source type and removed recorded JSON responses. JSON profiles remain in-memory per run, and source deletion removes the uploaded JSON and every document-scoped derived record.
- Evidence: frontend ESLint and Vitest (32/32), then `bin/agent-validate targeted` (Ruff, Mypy, backend pytest 114/114) all passed.

## 2026-09-09 — Compact mapping-issue details

- Replaced the expanded repeated mapping-issue text in every product-detail section with a native collapsed disclosure. The visible state shows only the issue count; exact evidence messages remain available on demand.
- Evidence: `bin/agent-validate targeted` passed (frontend lint/Vitest 32/32, backend Ruff/Mypy, backend pytest 114/114).

## 2026-09-09 — Material-unusable source inspection

- Prevented empty image readings from being promoted to ordinary review, which previously produced a false error banner. A material-unusable image now displays its retained original material inline beneath the source header, with a larger preview available on demand.
- Evidence: `bin/agent-validate targeted` passed (frontend lint/Vitest 33/33, backend Ruff/Mypy, backend pytest 114/114).

## 2026-09-09 — Separate extraction, grounding, and investigation

- Primary extraction now returns the canonical candidate plus a reviewer narrative without provenance requirements. A separate full grounding call owns evidence records and JSON source facts. If needed, an application-owned `while` loop makes evidence-only investigation requests with the complete remaining ungrounded-field list; they cannot rewrite extraction values.
- Removed LangChain agent creation, tools, tool/model-call middleware, and model-selected tool calls. The pipeline is fully application-controlled: code selects every call, input, repeat decision, three-run limit, validation, and result routing.
- A grounding failure or incomplete JSON grounding retains a structurally valid candidate for review rather than reporting a technical extraction failure.
- Replaced the primary model's reused canonical schema with an extraction-only response schema that forbids document and line-item evidence fields. Evidence is now structurally exclusive to grounding and investigation output.
- Evidence: app health check passed; focused semantic-agent, JSON, and LangChain integration tests passed (19); Ruff passed on touched backend modules.
- Review: `bin/agent-review wrap-up` found no configured independent provider. Isolated checks covered evidence ownership, failure retention, documentation, and handoff completeness; no additional finding was identified.

## 2026-09-09 — Complete application-controlled evidence loop

- Grounding and investigation now return strict field-specific claims rather than canonical data or loose source facts.
- Python validates the canonical destination, addressable source reference, claimed source value, direct candidate equality, and JSONPath existence/value before attaching evidence.
- A full-grounding failure no longer ends the semantic flow; all populated fields enter the same maximum-three-run investigation loop.
- Removed the obsolete JSON whole-extraction retry contract. Invalid claims are discarded and the semantic evidence loop owns follow-up.
- Renamed the runtime module and logger from agent terminology to semantic extraction terminology. No LangChain agent, tools, middleware, or model-selected transition remains.
- Google Gemini 3.5 Flash Lite is now the only configured semantic provider; the OpenRouter provider chain and dependency were removed at the user's request.
- Added safe start/completion/failure logs around every extraction, grounding, and investigation model call, including provider, model, duration, and counts but no source or prompt content.
- Validation: FastAPI started successfully and `GET /health` returned `ok`; `bin/agent-validate targeted` passed frontend lint/Vitest (33 tests), backend Ruff/Mypy, and backend pytest (118 tests).
- Review: no independent review provider was configured. An isolated pass confirmed extraction cannot emit evidence, grounding cannot rewrite values, invalid claims are rejected before persistence, the loop receives all remaining fields together, and the run limit is application-owned.
- No commit was created, per user instruction.

## 2026-09-09 — Explicit ingredient strength grounding and reviewer labeling

- Grounded and assessed combination drug strengths at the composite potency level (`product.strength[i]`) rather than breaking each `Strength` down into detached `unit` and default `per_value: 1` leaves.
- Formatted strength mapping issues explicitly with their active ingredient and potency (`{ingredient} strength {potency}`, e.g. `Tenofovir disoproxil fumarate strength 300 mg / 1 tablet`), eliminating ambiguous messages like `Strength 1 · Unit` and `Strength 1 · Per Value`.
- In `ProductDetailDrawer.vue`, anchored strength issues with a visual indicator directly next to the **Strength** field in the Product Identity card, while formatting issue details using the exact active ingredient name.
- Added bidirectional hierarchical evidence matching so evidence linked to `product.strength`, `product.strength[i]`, or `product.strength[i].value` cleanly satisfies mapping confidence.
- Validation: `bin/agent-validate targeted` passed with 122 backend pytest tests, 35 frontend Vitest tests, and clean Ruff, Mypy, and ESLint checks.
- No commit was created, per user instruction.

## 2026-09-09 — Derived pack price evidence reuse without phantom mapping issues

- Investigated user report of 0 orchestrator issues vs. 1 mapping issue per product on `Novara Farmaceutici S.p.A. quotation` (Azimax 250 and Dexafar).
- Root cause: The orchestrator and grounding stages successfully extracted and grounded all 66 source fields with 0 ungrounded fields and 0 extraction issues. However, during post-extraction commercial normalization, `commercial.py` mathematically derived `pack_price = quoted_price * units_per_pack` (e.g. `0.134 * 6 = 0.804` and `0.41 * 25 = 10.25`). Because the raw source email contained only the unit price and pack size, `pack_price` had no direct source evidence record, causing `assess_mapping_confidence` to flag a phantom `missing_mapping_evidence` issue on `pricing.pack_price`.
- Fix:
  1. Updated `commercial.py` to copy unit price evidence with `extraction_method="derived_from_quoted_price"` when computing `pack_price = quoted_price * units`.
  2. Updated `confidence.py` so `assess_mapping_confidence` inherits `quoted_price.amount` evidence for `pack_price` whenever `pack_price` is equal to or calculated from `quoted_price * units_per_pack`.
- Added regression test `test_derived_pack_price_reuses_quoted_price_mapping_evidence` in `backend/tests/test_confidence.py`.
- Validation: `bin/agent-validate targeted` passed cleanly with 36 Vitest tests, 123 pytest tests, 0 ESLint warnings, and 0 Ruff/Mypy errors. Verified live API response for document `d93ada79` now returns 0 mapping issues across all 3 line items.
- No commit was created, per user instruction.

## 2026-09-09 — CSV export review status and empty delimiter suppression

- Added user-facing `review_status` column to CSV export headers and rows (`SOURCE_HEADERS`), formatting statuses with plain-language labels matching the UI (`Needs review`, `Pre-approved`, `Approved`, `Rejected`, `Material unusable`, `Extraction failed`).
- Updated `_aligned` in `backend/app/csv_export.py` to return an empty string when all values in a parallel evidence/review list are empty/`None`, eliminating visual delimiter chains (`;;;;;;;;;;;;;;;;`) in spreadsheet viewers for non-superseded paths while preserving index alignment when data exists.
- Updated `backend/tests/test_csv_export.py` with assertions for `review_status` across completed and failed sources and verified `evidence_superseded_paths` is clean.
- Validation: `bin/agent-validate targeted` passed cleanly with 36 Vitest tests, 123 pytest tests, 0 ESLint warnings, and 0 Ruff/Mypy errors.
- No commit was created, per user instruction.

