# Worksheet: di-10-langchain-gemini

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks
- Integrate LangChain with Google Gemini (`gemini-3.1-flash-lite`) across all 4 document extraction sources (JSON, Email, PDF, OCR).
- Follow PRD Sections 3.1, 5, 31, 42, 43: deterministic fast path and PII redaction first, LangChain for semantic ambiguity and structured Pydantic output, followed by deterministic commercial validation.
- Provide graceful offline fallback for test reproducibility and zero-cost local CI.
- Full validation passes (`bin/agent-validate full`).

## Context and constraints
- Strictly use `gemini-3.1-flash-lite`. Exclude `gemini-2.5-flash-lite` and `gemini-2.0-flash`.
- Model output must strictly adhere to `CanonicalQuotation` and `MappingProposal`.
- Deterministic rules must validate all commercial calculations and confidence scores.

## Plan
1. Add `langchain>=1.4.0` and `langchain-google-genai>=4.4.0` to `backend/pyproject.toml`.
2. Add `gemini_api_key` and `gemini_model="gemini-3.1-flash-lite"` to `Settings`.
3. Implement `LangChainSemanticExtractor` in `backend/app/domain/langchain_extractor.py`.
4. Connect LangChain extractor across workers (`email_extraction.py`, `pdf_extraction.py`, `ocr.py`) and novel JSON mapping (`documents.py`).
5. Add comprehensive unit and integration tests in `backend/tests/test_langchain_gemini.py`.
6. Update system docs and verify full suite passes.

## Work log and evidence
- Added `langchain>=1.4.0` and `langchain-google-genai>=4.4.0` to `backend/pyproject.toml`. Installed via `uv sync --project backend`.
- Extended `Settings` in `backend/app/core/settings.py` with `gemini_api_key`, `gemini_model="gemini-3.1-flash-lite"`, and automatic resolution via `resolved_gemini_api_key` (checking `GEMINI_API_KEY`, `GOOGLE_API_KEY`, and `AXMED_GEMINI_API_KEY`).
- Built `LangChainSemanticExtractor` in `backend/app/domain/langchain_extractor.py`:
  - Structured `CanonicalQuotation` extraction for email, PDF, and OCR.
  - Implements email chronological discourse resolution and supersession evidence generation (PRD §43).
  - Novel JSON schema mapping proposal returning `MappingProposal` (PRD §31).
- Added `LangChainSemanticMappingProvider` and `ChainedSemanticMappingProvider` in `backend/app/domain/schema_mapping.py`.
- Connected LangChain extraction into background workers:
  - `backend/app/workers/email_extraction.py`
  - `backend/app/workers/pdf_extraction.py`
  - `backend/app/workers/ocr.py`
- Connected LangChain mapping provider into `backend/app/api/application.py` and `backend/app/application/documents.py`.
- Added 7 comprehensive unit/integration tests in `backend/tests/test_langchain_gemini.py` covering email, PDF, OCR, novel schema mapping, deterministic schema cache bypass, and offline fallback.
- Fixed TypeScript configuration in `frontend/vite.config.ts` to allow typechecking without nested vite conflict.

## Tests, app run, and validation
- `PYTHONPATH=backend uv run --project backend pytest backend/tests/test_langchain_gemini.py -v`: 7 passed in 0.44s.
- `PYTHONPATH=backend uv run --project backend ruff check backend`: Clean (All checks passed!).
- `PYTHONPATH=backend uv run --project backend pytest backend/tests -v`: 57 passed in 2.13s.
- `bin/agent-validate full`:
  - Frontend ESLint: clean (0 warnings)
  - Frontend Vitest: 7 passed
  - Frontend production build: succeeded in 257ms
  - Playwright E2E: 2 passed in 3.1s
  - Backend Ruff: clean
  - Backend Pytest: 57 passed in 2.11s

## Review findings and resolutions
- PRD alignment: strictly adheres to the deterministic-first architecture where known schemas and native formats are processed deterministically first; LangChain is invoked for ambiguous extraction; commercial rules run deterministically after; and human confirmation saves to SQLite schema memory for future zero-cost deterministic replay.
- Model constraint: strictly locked to `gemini-3.1-flash-lite`.

## Docs updated
- `docs/system/architecture.md`
- `docs/system/test-catalog.md`
- `docs/worksheets/di-10-langchain-gemini.md`

## Handoff / remaining work
- Ready for end-to-end live testing with a live `GEMINI_API_KEY` in `.env`.
- All automated checks 100% green.

## Final commit and tag
- Tag: `worksheet/di-10-langchain-gemini` (pending user instruction to commit).
