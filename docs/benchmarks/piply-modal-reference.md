# Piply Modal OCR Benchmark Reference

> Purpose: record the prior `piply-modal` implementation used as the OCR deployment benchmark.
> Source inspected: `/Users/andrewsboateng/Projects/piply/piply-modal` on 2026-09-06.
> Reuse its deployment patterns as reference; do not copy its service into this repository unchanged.
> The Axmed app owns OCR routing, review status, PII policy, provenance, and retries through an `OcrClient` port.
> Live Modal deployment is authorized by the user as of 2026-09-06; the Axmed-owned service lives in `modal/`.
> Search terms: Modal, PaddleOCR, benchmark, OCR contract, deployment, Piply.

## What the benchmark proves

The previous implementation runs PaddleOCR 3.5.0 on a Modal T4 GPU behind FastAPI. It accepts PDFs/images, renders selected PDF pages with PyMuPDF, keeps an OCR engine warm at module scope, supports `start_page`/`max_pages`, exposes `/health` and `/ocr`, and includes a script for real endpoint latency measurements.

## What to retain

- Modal image build with pinned Python/Paddle/PaddleOCR dependencies and GPU allocation.
- Warm OCR-engine reuse, bounded page selection, PDF rasterization, temporary-file cleanup, health endpoint, and repeat-run latency measurement.
- A separate deployable OCR service rather than loading GPU dependencies into FastAPI/Huey workers.

## Required Axmed changes

| Area | Required integration change |
| --- | --- |
| Routing | `ParseQualityPolicy` selects explicit original page IDs after native parsing; send only those pages. The Modal service never decides review state. |
| Contract | Return original page number, line/word text, OCR confidence, bounds plus page dimensions/DPI—not only combined plain text. Include a versioned schema and safe provider/model/config/duration metadata. |
| Validation | Inspect content signatures; enforce byte/page/target-page/pixel/render limits; reject encrypted/corrupt PDFs; use a request-specific temp directory and safe generated names. |
| Security | Require backend-to-Modal authentication and authorization, structured safe errors, rate/concurrency limits, and no raw document/error logs. Document that selected raw pixels reach Modal before LLM PII redaction. |
| Reliability | Pass idempotency key, deadline, attempt, and correlation ID. Classify timeout, throttling, provider, invalid-response, and input errors so Huey can apply bounded retry only to transient failures. |
| Evidence | Persist OCR page/region coordinates and confidence as `field_evidence`; retain null/low-confidence values rather than guessing. |
| Testing | Use recorded OCR responses for CI, contract tests against the service schema, and live smoke/latency runs after a user-authorized deploy. |

## Axmed OCR client contract

```text
ocr(bytes, media_type, selected_original_pages, idempotency_key, deadline) ->
  schema_version, provider/model/config/version, duration,
  pages[{original_page_number, width, height, dpi,
         lines[{text, confidence, polygon_or_bounds}]}]
```

The caller sends only pages selected by `ParseQualityPolicy`. The response is provider evidence, not a canonical quotation; normalization and semantic interpretation remain inside the Axmed pipeline.

The checked-in `app.extraction.ocr_contract` now enforces this response shape locally. The reference service's text-only response is therefore a benchmark input, not a deployable Axmed contract; the Axmed-owned service must add bounds, confidence, dimensions, DPI, version, and safe execution metadata before it can be wired in.

`app.extraction.ocr_client` sends this contract with a bounded deadline, idempotency key, selected original pages, and optional backend-to-service bearer credential. `app.extraction.image_processing` runs the OCR step in-process: it retains only redacted OCR evidence, emits safe stage events, and does not pretend OCR succeeded when no endpoint is configured.

## Deployment and benchmark gate

Deployment was authorized and completed on 2026-09-06. The health check, unauthorized-route check, degraded-image smoke checks, contract validation, and API-to-review smoke are recorded in `docs/worksheets/di-06-modal-ocr.md`. A repeated cold/warm benchmark with percentile and cost tracking remains the next operational benchmark task.
