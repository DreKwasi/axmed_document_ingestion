# Axmed Supplier Document Intelligence

> Intelligent multi-format quotation extraction and human-review pipeline for pharmaceutical procurement.

- 🌐 **Live Platform (Cloudflare Pages)**: [https://axmed-document-ingestion.pages.dev/](https://axmed-document-ingestion.pages.dev/)
- 🚀 **Live Backend API (Railway)**: [https://axmeddocumentingestion-production.up.railway.app](https://axmeddocumentingestion-production.up.railway.app) *(Docs: [/docs](https://axmeddocumentingestion-production.up.railway.app/docs))*

---

## Overview

Axmed receives supplier quotations in varied formats: structured JSON exports, native digital PDFs, multi-turn emails with price corrections, and degraded image scans. This platform extracts, normalizes, validates, and presents supplier offers for human review.

Key capabilities:
- **Source-Grounded JSON Extraction**: Every JSON document is interpreted independently; recovered facts retain exact JSONPaths and values, invalid claims are rejected, and uncertain normalization remains explicit instead of becoming a reusable schema rule.
- **Bounded Semantic Investigation**: One LangChain agent extracts the primary candidate, validates it through a deterministic tool, revisits the complete source while feedback changes, and returns a supported result or unresolved issues. It does not control routing, calculations, persistence, or human approval.
- **Commercial Validation**: Automatic derivation of unit prices from pack pricing, MOQ compliance checking, volume tier verification, and date validity.
- **Background Processing**: Reconnectable Server-Sent Events (SSE) via `Last-Event-ID`, with API-owned Python background tasks and SQLite-persisted progress.
- **Independent Batch Ingestion**: Upload folders or multiple files simultaneously with derived aggregate progress and isolated failure handling.
- **Privacy by Default**: Deterministic redaction scrubs email addresses and phone numbers before data reaches API background tasks or logs.

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
# (Optional) Add GEMINI_API_KEY and OPENROUTER_API_KEY in backend/.env for live semantic reasoning.
# The provider order is direct Gemini, OpenRouter Gemini, then OpenRouter gpt-oss-120b.

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
- **Vue 3 Review Desk**: [http://127.0.0.1:5173](http://127.0.0.1:5173)

### 3. Running Services Independently

If you prefer running services in separate terminal windows:

- **Terminal 1 — Backend Web API**:
  ```bash
  cd backend
  set -a; source .env; set +a
  uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
  ```
- **Terminal 2 — Frontend Dev Server**:
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
│   │   ├── api.py           # FastAPI setup and every public route
│   │   ├── documents.py     # Document intake, persistence, and review
│   │   ├── extraction/      # Parsing, extraction, confidence, and normalization
│   │   ├── models.py        # Persisted SQLAlchemy records
│   │   ├── database.py      # Database engine and migrations
│   │   └── security/        # Contact PII redaction
│   ├── migrations/          # Alembic versioned migrations
│   └── tests/               # Pytest suite (uploads, extraction, review, PII audit)
├── frontend/
│   ├── src/                 # Vue 3 Review Desk & Evaluation Lab
│   └── e2e/                 # Playwright end-to-end smoke tests
├── docs/
│   ├── system/              # Architecture, testing, conventions system docs
│   ├── worksheets/          # Implementation worksheets & session evidence
│   └── product/             # Product Requirements Document (PRD)
├── sample_documents/        # Synthetic supplier fixtures (JSON, EML, PDF, PNG, JPG)
├── backend/evals/           # Golden datasets, outputs, recorded extraction fixtures, and OCR fixtures
└── WRITEUP.md               # Architecture design & trade-off narrative
```
