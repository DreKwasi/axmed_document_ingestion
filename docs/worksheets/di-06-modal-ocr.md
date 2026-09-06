# DI-06 — Modal OCR deployment

> Goal: provide an Axmed-owned, authenticated PaddleOCR boundary for low-quality images and PDF pages.
> Source: `modal/ocr_service.py`; backend adapter: `app.workers.ocr_client`.
> Deployment: `axmed-paddle-ocr` on Modal, deployed 2026-09-06.
> Contract: schema `1.0`, selected original pages only, text/confidence/coordinates per line.
> Verification: health check, rejected unauthenticated request, two authenticated degraded-image OCR runs, and an API-to-review smoke run.
> Runtime: `bin/dev` migrates before starting Huey and sources ignored `backend/.env` for local configuration.
> Search terms: Modal, PaddleOCR, OCR, Huey, review, deployment.

## Result

The deployed service is available at `https://andrewsboateng137--axmed-paddle-ocr.modal.run/ocr`; `/health` returned `ok`. It uses the Modal secret `axmed-ocr-service` rather than accepting public OCR requests.

Authenticated checks completed against both supplied degraded fixtures:

| Fixture | Lines | Service duration |
| --- | ---: | ---: |
| `scan_02_lowres_fax_andina_p1.png` | 119 | 16,974 ms |
| `scan_03_glare_partial_andina_p1.jpg` | 83 | 15,317 ms |

The local isolated SQLite smoke then processed the glare image through ingest, Huey, Modal OCR, Gemini extraction, and a `needs_review` quotation with one line item. This is evidence of the integration path, not a quality claim for the model.

## Warm benchmark

Three authenticated runs of `scan_02_lowres_fax_andina_p1.png` on the deployed endpoint produced one page and 119 OCR lines per run. End-to-end wall-clock latency was p50 **3,494.21 ms** and p95 **4,551.45 ms**; provider processing was p50 **666 ms** and p95 **679.5 ms**. The command is reproducible through `modal/benchmark_ocr.py`. No cost or accuracy metric is recorded here: Modal billing data and approved human ground truth are required for those claims.

## Operational note

`backend/.env` is ignored and holds `AXMED_OCR_SERVICE_URL` plus the matching `AXMED_OCR_SERVICE_TOKEN`. Rotate the Modal secret and the backend value together. The service remains separate from the API and performs OCR only; canonical extraction and review status stay in the Axmed backend.
