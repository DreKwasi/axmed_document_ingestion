# Worksheet: upgrade-liteparse-v2

> Purpose: Upgrade LiteParse from v1.x wrapper to native Rust v2.x, eliminating the Node.js/CLI subprocess dependency in the backend.
> Created: 2026-09-08.

## Goal and acceptance checks

- Backend dependencies are updated to use `liteparse>=2.14.4`.
- The backend runtime no longer depends on Node.js, `npm`, or `node_modules/.bin/liteparse`.
- `backend/app/extraction/pdf_parser.py` parses PDFs in-process via the native Rust extension without spawning subprocesses or searching CLI paths.
- Redundant files (`backend/package.json`, `backend/package-lock.json`, and backend `node_modules`) are removed.
- Deployment configuration (`backend/railpack.json`) and documentation (`backend/README.md`) are updated to pure Python.
- All unit tests, contract checks, and evaluations pass without regressions.

## Context and constraints

- LiteParse v2 rewrote the engine in Rust and publishes pre-compiled native wheels with PyO3 bindings for Linux, macOS, and Windows.
- In v1, the Python `liteparse` package was a thin wrapper around the `@llamaindex/liteparse` Node CLI, requiring Node.js, npm installation, and CLI path resolution in production.
- v2 dataclasses use snake_case (`page.page_num`, `page.text_items`), and constructor options (`ocr_enabled=False`, `quiet=True`) replace runtime CLI flags.

## Plan

1. Create worksheet and initialize tracking.
2. Update `backend/pyproject.toml` to `"liteparse>=2.14.4"` and sync virtual environment with `uv sync`.
3. Update `backend/app/extraction/pdf_parser.py` to use native in-process `LiteParse` with dataclass serialization.
4. Remove `backend/package.json` and `backend/package-lock.json` and prune backend `node_modules`.
5. Update `backend/railpack.json` to remove Node 22 packages, npm build steps, and `/app/node_modules/.bin` path.
6. Update `backend/tests/test_pdf_parser.py` to test in-process native parsing and remove obsolete CLI-missing tests.
7. Update documentation (`backend/README.md`, `docs/system/test-catalog.md`).
8. Run `bin/agent-validate targeted` and `bin/agent-validate full`.

## Work log and evidence

- Updated `backend/pyproject.toml` to depend on `liteparse>=2.14.4`.
- Ran `uv sync --project backend`, which updated `backend/uv.lock` and installed `liteparse==2.14.4` while cleanly removing transitive v1 packages.
- Refactored `backend/app/extraction/pdf_parser.py`:
  - Removed `_liteparse_cli_path()`, `BACKEND_ROOT`, and `shutil`.
  - Instantiated in-process `LiteParse(ocr_enabled=False, quiet=True)`.
  - Mapped v2 Python dataclass attributes (`page_num`, `text_items`).
  - Serialized `raw_representation={"page": page.page_num, **dataclasses.asdict(page)}`.
- Deleted obsolete `backend/package.json`, `backend/package-lock.json`, and backend `node_modules`.
- Simplified `backend/railpack.json` to `{ "$schema": "https://schema.railpack.com", "provider": "python" }`, removing Node 22 and npm commands.
- Updated `backend/tests/test_pdf_parser.py` to replace the obsolete CLI-resolution test with `test_native_pdf_parser_fails_fast_when_pdf_content_is_corrupt`.
- Updated `backend/README.md` to remove Node installation steps for backend PDF parsing.
- Updated `docs/system/test-catalog.md` and `docs/agent-feedback.md`.

## Tests, app run, and validation

- `PYTHONPATH=backend uv run --project backend pytest backend/tests/test_pdf_parser.py -q`: 8 passed in 0.46s.
- `PYTHONPATH=backend uv run --project backend pytest backend/tests -q`: 92 passed in 6.12s.
- `PYTHONPATH=backend uv run --project backend ruff check backend`: All checks passed.
- `cd backend && uv run mypy app`: Success: no issues found in 26 source files.
- `backend/bin/run-evals`: 5 passed in 0.70s.
- `bin/agent-validate targeted`: Passed (frontend lint/vitest, backend ruff/mypy/pytest).
- `bin/agent-validate full`: Passed (frontend lint, vitest 22 passed, build passed, Playwright E2E 2 passed, backend ruff/mypy/pytest 92 passed, evals 5 passed).
- Live execution test: uploaded `farmaceutica_andina_proforma_FA-COT-2026-118.pdf` via TestClient, received HTTP 201 with 2 `native_pdf_page` artifacts and `good` quality.

## Review findings and resolutions

- Verified that `raw_representation["page"]` is preserved for downstream table planning and redaction pipelines.
- Confirmed that `quiet=True` suppresses LiteParse stdout timing lines during extraction.
- Confirmed that backend Docker / Railpack image is now a pure Python container with no Node 22 overhead.

## Docs updated

- `backend/README.md`: Removed `npm install --prefix backend` and `@llamaindex/liteparse` Node requirements.
- `docs/system/test-catalog.md`: Updated `backend/tests/test_pdf_parser.py` description.
- `docs/agent-feedback.md`: Added observation on upgrading to native Rust LiteParse v2.

## Handoff / remaining work

- Commit changes when ready. No remaining tasks.

## Final commit and tag

