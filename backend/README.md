# Axmed Document Intelligence — Backend API

FastAPI REST & Server-Sent Events (SSE) service backed by SQLite WAL. It uses API-owned Python background tasks for multi-format supplier document extraction (JSON, Native PDF, EML, Image Scans), deterministic-first progressive parsing, contact PII redaction, LangChain semantic reasoning powered by Google Gemini (`gemini-3.1-flash-lite`), and commercial validation for pharmaceutical procurement.

---

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** (fast Python package and project manager)

---

## Quick Setup & Installation

From the repository root or within `backend/`:

```bash
# 1. Install all dependencies (including dev and test groups)
uv sync --project backend --all-groups

# 2. Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env to configure your GEMINI_API_KEY if testing live LLM reasoning
```

---

## Configuration & Environment Variables

The backend configuration is managed by `app/config.py`. Variables can be defined in `backend/.env` or passed via system environment variables:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | *(None)* | Google Gemini API key for live LangChain semantic reasoning |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Model name for LangChain structured extraction and per-document JSON semantic extraction |
| `GEMINI_REQUEST_TIMEOUT_SECONDS` | `60` | Request timeout for Google Gemini API calls |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy SQLite database URL for operational persistence; relative SQLite paths resolve from `backend/` |
| `UPLOAD_DIR` | `data/uploads` | Local directory for storing original uploaded files; relative paths resolve from `backend/` |
| `MAX_UPLOAD_BYTES` | `15728640` (15 MB) | Maximum permitted file upload size |
| `OCR_SERVICE_URL` | `https://andrewsboateng137--axmed-paddle-ocr.modal.run/ocr` | Modal PaddleOCR microservice endpoint URL |
| `OCR_SERVICE_TOKEN` | *(None)* | Bearer authentication token for Modal OCR service |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed CORS origins for the Vue frontend |

---

## Running the Backend

The backend is one FastAPI process. It runs API-owned background tasks after source intake responses have been sent.

### Option A: Supervised (Recommended)
From the repository root, start the FastAPI server and Vue frontend together:

```bash
make dev
# or: bin/dev
```

### Option B: Running Processes Independently

#### 1. Apply Database Migrations
Ensures all Alembic migrations are applied to `data/app.db`:

```bash
PYTHONPATH=backend uv run --project backend python -c 'from pathlib import Path; from app.config import get_config; from app.database import run_migrations; run_migrations(get_config().database_url, Path.cwd())'
```

#### 2. Start FastAPI Web Server
Runs the API server on `http://127.0.0.1:8000` with hot-reload:

```bash
set -a; source .env; set +a
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
- **OpenAPI Interactive Documentation**: Visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) (Swagger UI) or `/redoc`.

## Testing & Quality Checks

Run tests and linters using `uv`:

```bash
# Run all 57 backend tests (commercial rules, schema memory, LangChain, PII audit)
PYTHONPATH=backend uv run --project backend pytest backend/tests -v

# Run targeted test suites
PYTHONPATH=backend uv run --project backend pytest backend/tests/test_langchain_gemini.py -v
PYTHONPATH=backend uv run --project backend pytest backend/tests/test_batch_processing.py -v
PYTHONPATH=backend uv run --project backend pytest backend/tests/test_pii_audit.py -v

# Run Ruff linter
PYTHONPATH=backend uv run --project backend ruff check backend
```

---

## Key API Endpoints

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/documents` | Upload one or many documents (`.json`, `.pdf`, `.eml`, `.png`, `.jpg`) |
| `GET` | `/api/v1/documents` | List all ingested documents |
| `GET` | `/api/v1/documents/{id}` | Retrieve document, quotation data, validation issues, and provenance |
| `GET` | `/api/v1/documents/{id}/events` | Retrieve persisted processing activity |
| `GET` | `/api/v1/documents/{id}/events/stream` | SSE live stream with `Last-Event-ID` reconnection replay |
| `POST` | `/api/v1/documents/{id}/reextract` | Explicitly re-extract a stored JSON source without changing completed review audit history |
| `POST` | `/api/v1/documents/{id}/reviews/{action}` | Submit reviewer action (`approve`, `reject`, or line-item field `correct`) |

Unexpected upload failures are logged with a full traceback, safe file metadata, and the inbound Railway request ID when available. The handled error response repeats that value in `X-Request-ID` and the JSON detail so a browser report can be correlated with deployment logs without logging source contents or filenames.

---

## Directory Architecture

```text
backend/
├── app/
│   ├── api.py           # FastAPI setup and every public route
│   ├── documents.py     # Document intake, persistence, serialization, and review
│   ├── extraction/      # Parsers, extraction pipelines, confidence, and normalization
│   ├── models.py        # SQLAlchemy records
│   ├── database.py      # SQLite engine, sessions, and migrations
│   ├── evaluations.py   # Developer evaluation operations used by backend/bin/run-evals
│   └── security/        # Contact PII redaction
├── migrations/          # Versioned Alembic database migrations
└── tests/               # Pytest suite
```
