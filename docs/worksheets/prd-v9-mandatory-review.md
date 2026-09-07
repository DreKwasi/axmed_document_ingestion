# Worksheet: prd-v9-mandatory-review

> Purpose: durable handoff trace for the PRD v9 confidence, semantic extraction, and mandatory-review update.

## Goal and acceptance checks

- Replace auto-accept / exception-only routing with mandatory human review for every successful extraction.
- Keep confidence as field-level evidence that prioritizes review; do not use it as a skip-review decision.
- Use the semantic extractor, not supplier-shaped regexes, to recover quotation/RFQ references and explicit origin facts from PDFs.
- Make confidence explanations readable and non-duplicative in the reviewer UI.
- Re-extract the existing stored PDF and verify the recovered commercial metadata.

## Context and constraints

- The canonical PRD is `docs/product/axmed_document_intelligence_prd.md`; versioned Downloads copies are input, not parallel project PRDs.
- No fixed critical-field list: absence is not a confidence failure.
- Corrections retain before/after history and keep a source pending until explicit approval or rejection.

## Plan

1. Update the lifecycle, persistence defaults, queue query, migration, and UI labels.
2. Strengthen the generic LLM semantic prompt for quote/RFQ references and explicit facility-origin reasoning.
3. Replace raw repeated factor chips with one source/product/check summary per product drawer.
4. Migrate, re-extract, test, run the app, and review the diff.

## Work log and evidence

- Removed the proposed deterministic PDF-enrichment module before it was committed. No supplier-specific PDF regular expressions remain.
- Prompt version `canonical-quotation-v5` instructs the LLM to distinguish supplier quotation reference from buyer RFQ reference; extract supplier address country, Incoterm named-place country, and product origin only from an explicit manufacture/origin statement, including an all-items facility statement linked to the supplier address. A delivery location never becomes origin evidence.
- `20260907_17_mandatory_human_review` adds `quotations.has_corrections` and backfills legacy document, quotation, and field review states to `pending_review`.
- The existing Andina PDF was re-extracted through Gemini after migration. Verified values: `FA-COT-2026-118`, `AXMED-RFQ-2026-0233`, `FOB Cartagena` with delivery country `Colombia`, supplier country `Colombia`, and six product origin values of `Colombia` (no city stored as origin).

## Tests, app run, and validation

- Full backend suite: 89 passed; recorded evaluations: 5 passed.
- Vue Vitest suite: 10 passed; frontend lint and production build passed.
- Playwright browser suite: 2 passed.
- API was restarted after migration; `GET /api/v1/documents` and the PDF detail endpoint confirmed the re-extracted persisted fields and `pending_review` status.
- Live narrow-width browser check confirmed Home, the mobile detail card, `Against RFQ`, delivery country, `Country of origin: Colombia`, and the deduplicated confidence summary.

## Review findings and resolutions

- Supplier-specific regex matching would overfit a single document. Removed it and made the semantic extraction prompt generic instead.
- Raw factorized reasons repeated the same diagnostic strings across fields. The frontend now presents a concise, deduplicated confidence summary and preserves detailed raw evidence only for audit/API use.
- Error-level review issues remain blockers for approval, but do not change the lifecycle status away from `pending_review`.

## Docs updated

- Canonical PRD, implementation plan, architecture, context glossary, and test catalog now describe mandatory human review and generic semantic PDF extraction.

## Handoff / remaining work

- No known remaining work.

## Final commit and tag

- Pending commit and `worksheet/prd-v9-mandatory-review` tag.
