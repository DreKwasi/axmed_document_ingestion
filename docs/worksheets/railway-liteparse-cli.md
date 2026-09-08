# Worksheet: railway-liteparse-cli

> Purpose: make the PDF parser's native CLI dependency explicit in Railway builds.
> Created: 2026-09-08.

## Goal and acceptance checks

- Railway installs a pinned Node runtime and LiteParse CLI alongside the Python API.
- The CLI is present on runtime `PATH` and PDF uploads parse without runtime package downloads.
- Deployment requirements and tests are documented.

## Context and constraints

- JSON, email, and image uploads work in production; PDF uploads return an unexpected 500.
- The Python `liteparse` 1.2.1 wrapper launches the separate `@llamaindex/liteparse` CLI.
- Local PDF reproduction timed out after 60 seconds because the wrapper fell back to `npx` without a locally installed CLI.

## Plan

1. Add and lock the backend Node runtime dependency.
2. Configure the Railway Python build to include Node and the installed CLI at runtime.
3. Verify CLI resolution and the focused native-PDF upload.

## Work log and evidence

- Added pinned `@llamaindex/liteparse` 2.14.4 production dependency and npm lockfile under `backend/`.
- Added a Python-provider Railpack configuration with Node 22, locked npm installation, runtime `node_modules`, and CLI `PATH`.
- Changed the PDF adapter to resolve `backend/node_modules/.bin/liteparse` (or an explicit system binary) and fail immediately when absent; it no longer permits the wrapper's runtime `npx` fallback.

## Tests, app run, and validation

- Before: the focused native-PDF upload waited 60 seconds for `npx` and returned 422; production returned 500 when the CLI runtime was absent.
- `liteparse --version` with the locked backend binary — resolved successfully.
- Focused parser/upload checks — 3 passed in 0.38 seconds.
- Ruff on the changed parser and tests — passed.
- Complete PDF/upload suites — 13 passed.
- `bin/agent-validate targeted` — frontend 16 passed; backend 92 passed; Ruff and mypy passed.
- `bin/agent-validate full` — frontend lint/build passed, Playwright 2 passed, backend 92 passed, recorded evaluations 5 passed.

## Review findings and resolutions

- Independent reviewer CLI is not configured. Isolated review confirmed the CLI version is locked, no runtime package download remains, missing dependency failure is immediate, and the production build retains both Node and `node_modules`.

## Docs updated

- Updated backend runtime setup and test catalog.

## Handoff / remaining work

- Deploy the Railway backend with service root `backend/`, confirm the build contains `Install LiteParse CLI`, then upload the PDF fixture through the production frontend.

## Final commit and tag
