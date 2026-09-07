# Worksheet: DI-13 architecture conformance

> Purpose: compare the implemented pipeline against the current PRD architecture.
> Scope: parser, durable artifacts, provenance, confidence, telemetry, and operational boundaries.
> Status: LiteParse and the three audited persistence gaps are implemented and validated.
> Source of truth: `docs/product/axmed_document_intelligence_prd.md`, sections 5–14, 29, and 44.
> Supersession: deterministic PII redaction is intentional; Presidio is deferred by user direction.
> Non-goal: deployment and commits are not authorized in this worksheet.
> Next: keep corpus evaluations and live provider telemetry under regression coverage.

## Corrected

- Native PDFs now use LlamaIndex LiteParse only. `pypdf` and `pdfplumber` have been removed.
- LiteParse table reading order is the sanitized semantic-extraction input; clean PDF pages still avoid OCR.

## Closed gaps

1. **Durable parsed artifacts and source coordinates.** Redacted LiteParse page output and supplied geometry now persist as page artifacts; raw source documents remain separately available only through the reviewer source route.
2. **Field-level provenance and confidence service.** `field_evidence` now stores relational evidence beside the canonical payload. Confidence is recalculated from extraction method, OCR/parser quality, and validation failures; reviewer corrections remain fully confident when uncontradicted.
3. **Model telemetry.** `model_invocations` now stores provider-reported input tokens, output tokens, and estimated cost when available. Unknown provider metrics remain null rather than fabricated.

## Remaining hardening

- The implementation plan calls for mypy, but it is neither in the development dependencies nor in `bin/agent-validate`. Add it after the above functional gaps so type coverage protects the new provenance types.
