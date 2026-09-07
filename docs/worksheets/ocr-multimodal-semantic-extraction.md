# Worksheet: ocr-multimodal-semantic-extraction

> Purpose: compare two independent Gemini readings of an OCR image without deterministic row reconstruction.
> Constraint: preserve OCR geometry for audit/debugging, but do not use it as Gemini mapping input.
> Git: the user requested no commits.

## Goal and acceptance checks

- The OCR-assisted path sends Gemini readable OCR page text only; it does not receive OCR bounding boxes, coordinates, or row-mapping instructions.
- The direct-vision path sends Gemini the original image independently.
- Both results are persisted as peers. Neither result is selected or merged automatically.
- The original OCR response remains stored in its redacted evidence record.
- Existing quotation normalization, validation, failure handling, and review behavior remain unchanged.
- Targeted and full validation pass, and the running path is exercised.

## Context and constraints

- PaddleOCR line order can place values against the wrong apparent row.
- The source media is authoritative; OCR text is a transcription aid.
- No deterministic OCR table extraction is introduced.

## Plan

1. Add regression tests for the OCR-to-Gemini context and multimodal message.
2. Run OCR-assisted text extraction and direct-image vision extraction independently.
3. Update requirements and architecture documentation.
4. Run targeted checks, the application path, review, and full validation.

## Work log and evidence

- 2026-09-07: The old implementation passed the complete redacted `OcrResult`, including line confidence and bounds, to Gemini as JSON; the original source media was not sent.
- 2026-09-07: Implemented peer OCR-assisted and direct-vision image extraction attempts. A reviewer explicitly opens one result for quotation review; this does not discard the other result.

## Tests, app run, and validation

- Targeted peer-attempt and migration tests passed before an unrelated concurrent confidence-module change made the backend import fail.
- Frontend lint and production build pass.
- The local database migrated to `20260907_23`; the peer-attempt table has no selected-result column.
- Full backend validation and interactive app verification remain blocked until the confidence-module public interface is restored.

## Review findings and resolutions

- `bin/agent-review implementation` found no configured independent review provider. Isolated review checks confirm the two attempts have distinct inputs, do not share a winner-selection field, preserve the losing candidate, and require an explicit review action before canonical quotation persistence.

## Docs updated

- Product requirements, architecture, test catalog, and agent feedback reflect peer image attempts and explicit reviewer handoff.

## Handoff / remaining work

- Re-run targeted backend tests, `bin/agent-validate full`, and an image upload UI check after the concurrent confidence refactor is reconciled.

Pending.

## Final commit and tag

Not applicable: user explicitly requested no commits.
