# Worksheet: DI-05 native PDF parsing

> Purpose: establish a safe native-text boundary before semantic PDF extraction.
> Scope: PDF signature validation, page-level native text, quality signals, and OCR routing.
> Status: LiteParse-only native parsing, safe intake, and durable semantic orchestration are implemented; live semantic fidelity remains open under DI-07.
> Dependencies: DI-03 durable events and configured semantic resolver.
> Source requirements: PRD section 10 and Slice 5 in `docs/plans/implementation-plan.md`.
> Parser decision: use the PRD-mandated LlamaIndex LiteParse adapter behind `app.domain.pdf_parser`.
> Privacy rule: native text stays local until the resolver-boundary redaction step.

## Work log

- 2026-09-06: Replaced the initial parser with LiteParse. It is the sole native-PDF parser; its raw page JSON is retained as redacted model evidence without application-owned table reconstruction.
- 2026-09-06: Verified Farmaceutica Andina and Mekong PDFs: each has two native-text pages, preserves its quotation reference in reading order, and does not request OCR.
- 2026-09-06: PDF upload now retains the source under a generated name, persists redacted LiteParse page representations plus quality metadata, emits a durable parse event, and routes only poor pages to `needs_ocr`.
- 2026-09-06: Clean native PDFs create a durable extraction job. The worker sends redacted page text to an operator-configured structured resolver, applies commercial validation, records safe invocation metadata, and transitions the quotation to human review.

## Remaining

- Live LiteParse-to-LLM PDF fidelity remains open: Andina and Mekong runs are persisted as field-level failures in SQLite.
- Add page/source-location provenance for every PDF resolver result as the semantic contract begins returning it.
