# Worksheet: DI-05 native PDF parsing

> Purpose: establish a safe native-text boundary before semantic PDF extraction.
> Scope: PDF signature validation, page-level native text, quality signals, and OCR routing.
> Status: native PDF parsing, safe intake, and durable semantic orchestration are implemented.
> Dependencies: DI-03 durable events and configured semantic resolver.
> Source requirements: PRD section 10 and Slice 5 in `docs/plans/implementation-plan.md`.
> Parser decision: use maintained `pypdf` behind `app.domain.pdf_parser`, not a direct LiteParse dependency.
> Privacy rule: native text stays local until the resolver-boundary redaction step.

## Work log

- 2026-09-06: Added `parse_native_pdf`, with strict PDF signature/read checks and explicit `good`/`poor` quality for each page.
- 2026-09-06: Verified Farmaceutica Andina and Mekong PDFs: each has two native-text pages, preserves its quotation reference in reading order, and does not request OCR.
- 2026-09-06: PDF upload now retains the source under a generated name, persists page-level quality/character-count metadata without copying native text into API payloads, emits a durable parse event, and routes only poor pages to `needs_ocr`.
- 2026-09-06: Clean native PDFs create a durable extraction job. The worker sends redacted page text to an operator-configured structured resolver, applies commercial validation, records safe invocation metadata, and transitions the quotation to human review.

## Remaining

- Enforce page/source-location provenance for every PDF resolver result.
- Add PDF corpus evaluation before moving degraded-image work to the Modal client contract.
