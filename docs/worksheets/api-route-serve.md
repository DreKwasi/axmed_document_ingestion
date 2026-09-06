# Worksheet: api-route-serve

## Goal

- Restore `GET /api/v1/documents` for the running frontend and prevent stale dev servers from hiding newly added routes.

## Diagnosis and fix

- Reproduction: `curl -i http://127.0.0.1:8000/api/v1/documents` returned `405 Method Not Allowed` with `Allow: POST`.
- The current source already defines `@app.get("/api/v1/documents")`; the listener was an older Uvicorn process launched without reload.
- Restarted the exact project process; the endpoint now returns `200 OK`.
- Updated `bin/dev` to launch Uvicorn with `--reload`.

## Validation

- `bash -n bin/dev`: passed.
- `GET /api/v1/documents`: `200`.
- `pytest backend/tests/test_pdf_parser.py -q`: 7 passed.

## Handoff

- The restarted backend is serving port 8000. Future `bin/dev` sessions reload route changes automatically.
