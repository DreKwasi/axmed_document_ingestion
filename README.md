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
- **Python 3.12+** with [uv](https://docs.astral.sh/uv/)
- **Node.js 22+** with npm

### 1. Install Dependencies & Configure Environment
```bash
# Backend setup
uv sync --project backend --all-groups
cp backend/.env.example backend/.env
# (Optional) Add your GEMINI_API_KEY in backend/.env for live LangChain Gemini reasoning

# Frontend setup
npm --prefix frontend install
cp frontend/.env.example frontend/.env
```

### 2. Start Both Services Together (Recommended)
```bash
make dev
# or: bin/dev
```
This concurrently boots:
- **FastAPI API**: [http://127.0.0.1:8000](http://127.0.0.1:8000) (OpenAPI interactive docs at `/docs`)
- **Huey Worker**: Listens on SQLite queue (`data/tasks.db`) for background extraction jobs
- **Vue 3 Review Desk**: [http://127.0.0.1:5173](http://127.0.0.1:5173)

### 3. Running Services Independently

If you prefer running services in separate terminal windows:

- **Terminal 1 — Backend Web API**:
  ```bash
  cd backend
  set -a; source .env; set +a
  uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
  ```
- **Terminal 2 — Backend Huey Worker**:
  ```bash
  cd backend
  set -a; source .env; set +a
  uv run huey_consumer.py app.workers.tasks.huey
  ```
- **Terminal 3 — Frontend Dev Server**:
  ```bash
  npm --prefix frontend run dev
  ```

For in-depth service-specific options, architecture diagrams, and testing guides, see:
- 📖 **[Backend Setup & Architecture Guide](file:///Users/andrewsboateng/Projects/axmed-takehome/backend/README.md)**
- 📖 **[Frontend Setup & Feature Tour Guide](file:///Users/andrewsboateng/Projects/axmed-takehome/frontend/README.md)**

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
make eval    # Run backend evaluation regression tests and persist a recorded SQLite run
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
├── backend/evals/           # Golden datasets, outputs, mappings, and OCR fixtures
└── WRITEUP.md               # Architecture design & trade-off narrative
```
