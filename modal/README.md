# Axmed OCR service

> Purpose: deploy Axmed's PaddleOCR boundary to Modal.
> Entry point: `ocr_service.py`.
> Contract: JSON/base64 input and versioned line-level OCR output consumed by `app.workers.ocr_client`.
> Security: requires the `axmed-ocr-service` Modal secret with `AXMED_OCR_SERVICE_TOKEN`.
> Deploy only after setting the same token in `AXMED_OCR_SERVICE_TOKEN` for the backend.
> Search terms: Modal, PaddleOCR, OCR, deploy, service token.

Install the CLI, set the secret, then deploy:

```sh
uvx modal secret create axmed-ocr-service AXMED_OCR_SERVICE_TOKEN=<long-random-token>
uvx modal deploy ocr_service.py
```

Set the printed `/ocr` URL as `AXMED_OCR_SERVICE_URL` and the same random token as `AXMED_OCR_SERVICE_TOKEN` in the backend environment. The endpoint accepts only the versioned contract; it does not accept browser uploads directly.

Measure a deployed image endpoint without retaining OCR text:

```sh
set -a; source ../backend/.env; set +a
uvx --from modal python benchmark_ocr.py ../backend/evals/fixtures/ocr/scan_02_lowres_fax_andina_p1.png --runs 3
```
