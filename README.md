# Axmed Supplier Document Intelligence

> Intelligent multi-format quotation extraction and human-review pipeline for pharmaceutical procurement.

---

## Overview

Axmed receives supplier quotations in varied formats: structured JSON exports, native digital PDFs, multi-turn emails with price corrections, and degraded image scans. This platform extracts, normalizes, validates, and presents supplier offers for human review.

Key capabilities:
- **Schema-Learning & Memory**: Novel schemas are confirmed once; subsequent uploads with matching fingerprints run deterministically with **zero LLM calls** and sub-second latency.
- **Commercial Validation**: Automatic derivation of unit prices from pack pricing, MOQ compliance checking, volume tier verification, and date validity.
- **Durable Processing**: Reconnectable Server-Sent Events (SSE) via `Last-Event-ID` backed by SQLite WAL and local `SqliteHuey` background queue.
- **Independent Batch Ingestion**: Upload folders or multiple files simultaneously with derived aggregate progress and isolated failure handling.
- **Privacy by Default**: Deterministic redaction scrubs email addresses and phone numbers before data reaches background workers or logs.

See [WRITEUP.md](file:///Users/andrewsboateng/Projects/axmed-takehome/WRITEUP.md) for the detailed architecture narrative and production scaling roadmap.

---

## Quick Start

### Prerequisites
- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- Node.js 22+ with npm

### 1. Install Dependencies
```bash
uv sync --project backend --all-groups
npm --prefix frontend install
```

### 2. Start Application
```bash
make dev
# or: bin/dev
```
- **Review Desk**: [http://127.0.0.1:5173](http://127.0.0.1:5173)
- **FastAPI API**: [http://127.0.0.1:8000](http://127.0.0.1:8000) (Interactive OpenAPI docs at `/docs`)

---

## Testing & Validation

Run the complete validation suite (Linters, Unit Tests, Type Checks, Frontend Build, and Playwright E2E):

```bash
bin/agent-validate full
```

Or run individual targets via `make`:

```bash
make lint    # Backend (Ruff) + Frontend (ESLint)
make test    # Backend (Pytest) + Frontend (Vitest)
make build   # Frontend production build (vue-tsc + vite)
make eval    # Run recorded evaluation benchmark against golden dataset
```

---

## Project Structure

```text
axmed-takehome/
├── backend/
│   ├── app/
│   │   ├── api/             # HTTP routes & composition
│   │   ├── application/     # Documents, batches, events, evaluations
│   │   ├── domain/          # Commercial rules, schema mapping, parsers
│   │   ├── infrastructure/  # SQLAlchemy models & SQLite database
│   │   ├── security/        # Contact PII redaction
│   │   ├── workers/         # Huey task queues & consumers
│   │   └── core/            # Configuration & settings
│   ├── migrations/          # Alembic versioned migrations
│   └── tests/               # Pytest suite (commercial rules, batches, PII audit)
├── frontend/
│   ├── src/                 # Vue 3 Review Desk & Evaluation Lab
│   └── e2e/                 # Playwright end-to-end smoke tests
├── docs/
│   ├── system/              # Architecture, testing, conventions system docs
│   ├── worksheets/          # Implementation worksheets & session evidence
│   └── product/             # Product Requirements Document (PRD)
├── sample_documents/        # Synthetic supplier fixtures (JSON, EML, PDF, PNG, JPG)
├── evals/                   # Golden dataset rubric and recorded mapping fixtures
└── WRITEUP.md               # Architecture design & trade-off narrative
```
