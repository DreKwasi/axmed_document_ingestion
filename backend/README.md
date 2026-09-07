# Axmed Document Intelligence — Backend API & Workers

FastAPI REST & Server-Sent Events (SSE) service backed by SQLite WAL and local `SqliteHuey` background queue. Implements multi-format supplier document ingestion (JSON, Native PDF, EML, Image Scans), deterministic-first progressive parsing, contact PII redaction, LangChain semantic reasoning powered by Google Gemini (`gemini-3.1-flash-lite`), and commercial validation for pharmaceutical procurement.

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

The backend configuration is managed by Pydantic Settings in `app/core/settings.py`. Variables can be defined in `backend/.env` or passed via system environment variables:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | *(None)* | Google Gemini API key for live LangChain semantic reasoning. *(Also reads `GOOGLE_API_KEY` or `AXMED_GEMINI_API_KEY`)* |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Model name for LangChain structured extraction and novel schema mapping |
| `AXMED_DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy SQLite database URL for operational persistence; relative SQLite paths resolve from `backend/` |
| `AXMED_TASK_DATABASE_PATH` | `data/tasks.db` | SQLite database file for Huey durable task queue; relative paths resolve from `backend/` |
| `AXMED_UPLOAD_DIR` | `data/uploads` | Local directory for storing original uploaded files; relative paths resolve from `backend/` |
| `AXMED_MAX_UPLOAD_BYTES` | `5242880` (5 MB) | Maximum permitted file upload size |
| `AXMED_OCR_SERVICE_URL` | *(None)* | Modal PaddleOCR microservice endpoint URL |
| `AXMED_OCR_SERVICE_TOKEN` | *(None)* | Bearer authentication token for Modal OCR service |
| `AXMED_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed CORS origins for the Vue frontend |

---

## Running the Backend

The backend comprises two main processes: the **FastAPI web server** and the **Huey background worker**.

### Option A: Supervised (Recommended)
From the repository root, start both the FastAPI server, Huey worker, and Vue frontend together:

```bash
make dev
# or: bin/dev
```

### Option B: Running Processes Independently

#### 1. Apply Database Migrations
Ensures all Alembic migrations are applied to `data/app.db`:

```bash
PYTHONPATH=backend uv run --project backend python -c 'from pathlib import Path; from app.core.settings import get_settings; from app.infrastructure.database import run_migrations; run_migrations(get_settings().database_url, Path.cwd())'
```

#### 2. Start FastAPI Web Server
Runs the API server on `http://127.0.0.1:8000` with hot-reload:

```bash
PYTHONPATH=backend uv run --project backend uvicorn app.api.application:app --host 127.0.0.1 --port 8000 --reload
```
- **OpenAPI Interactive Documentation**: Visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) (Swagger UI) or `/redoc`.

#### 3. Start Background Huey Worker
Listens on `data/tasks.db` to execute async jobs (PII redaction, LangChain reasoning, Modal OCR escalation):

```bash
PYTHONPATH=backend uv run --project backend huey_consumer.py app.workers.tasks.huey
```

---

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
| `POST` | `/api/v1/documents` | Upload a single document (`.json`, `.pdf`, `.eml`, `.png`, `.jpg`) |
| `POST` | `/api/v1/batches` | Upload multi-file batches with aggregate progress and failure isolation |
| `GET` | `/api/v1/batches` | List all batch ingestion jobs and derived progress states |
| `GET` | `/api/v1/batches/{id}` | Get status and child document states for a specific batch |
| `GET` | `/api/v1/documents` | List all ingested documents |
| `GET` | `/api/v1/documents/{id}` | Retrieve document, quotation data, validation issues, and provenance |
| `GET` | `/api/v1/documents/{id}/events` | SSE live stream with `Last-Event-ID` reconnection replay |
| `POST` | `/api/v1/documents/{id}/mapping/confirm` | Confirm proposed schema mapping; caches to SQLite memory |
| `POST` | `/api/v1/documents/{id}/reviews` | Submit reviewer action (`approve`, `reject`, or line-item field `correct`) |
| `POST` | `/api/v1/evaluations/runs` | Execute recorded evaluation or, when Gemini is configured, the live PDF pipeline |

---

## Directory Architecture

```text
backend/
├── app/
│   ├── api/             # FastAPI routers, app lifespan, and HTTP composition
│   ├── application/     # Use cases: documents, batches, evaluations, processing events
│   ├── domain/          # Core domain models:
│   │   ├── contracts.py           # CanonicalQuotation and Pydantic domain models
│   │   ├── commercial_rules.py    # Pack calculations, MOQ validation, confidence scoring
│   │   ├── langchain_extractor.py # LangChain + Gemini 3.1 Flash Lite structured engine
│   │   ├── schema_mapping.py      # Schema fingerprinting, memory cache, mapping providers
│   │   ├── email_parser.py        # MIME parsing, plain text extraction (no HTML execution)
│   │   ├── pdf_parser.py          # Native PDF table extraction and quality policy
│   │   ├── image_parser.py        # Signature and dimension validation for scans
│   │   └── ocr_contract.py        # Versioned OCR evidence models
│   ├── infrastructure/  # SQLAlchemy ORM models, SQLite engine, migrations runner
│   ├── security/        # Presidio and regex contact PII redaction
│   ├── workers/         # Huey task queues, consumers, and worker lifecycle
│   └── core/            # Configuration and Pydantic Settings
├── migrations/          # Versioned Alembic database migrations
└── tests/               # Pytest suite
```
