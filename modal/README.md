# Axmed OCR service

> Purpose: deploy Axmed's PaddleOCR boundary to Modal.
> Entry point: `ocr_service.py`.
> Contract: JSON/base64 input and versioned line-level OCR output consumed by `app.extraction.ocr_client`.
> Security: requires the `axmed-ocr-service` Modal secret with `AXMED_OCR_SERVICE_TOKEN`.
> Deploy only after setting the same token in `AXMED_OCR_SERVICE_TOKEN` for the backend.
> Search terms: Modal, PaddleOCR, OCR, deploy, service token.

Install the CLI, set the secret, then deploy:

```sh
uvx modal secret create axmed-ocr-service AXMED_OCR_SERVICE_TOKEN=<long-random-token>
uvx modal deploy ocr_service.py
```

Set the printed `/ocr` URL as `AXMED_OCR_SERVICE_URL` and the same random token as `AXMED_OCR_SERVICE_TOKEN` in the backend environment. The endpoint accepts only the versioned contract; it does not accept browser uploads directly.
