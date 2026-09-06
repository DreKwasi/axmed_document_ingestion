# Worksheet: favicon-404

## Goal

- Remove the browser favicon 404 from the frontend dev server.

## Diagnosis and fix

- Reproduction was a browser request for `/favicon.ico`; `frontend/index.html` had no icon link and `frontend/public` had no favicon asset.
- Added a local Axmed SVG favicon and declared it explicitly in the document head.

## Validation

- `curl http://127.0.0.1:5173/favicon.svg`: `200 image/svg+xml`.
- `npm --prefix frontend run lint`: passed.
- `npm --prefix frontend run build`: passed.
- `bash -n bin/dev`: passed.

## Handoff

- Browsers now use `/favicon.svg` and should no longer fall back to requesting `/favicon.ico`.
