# Axmed Supplier Document Intelligence: Architecture & Implementation Narrative

## Executive Summary

Pharmaceutical procurement at Axmed involves processing supplier quotations across heterogeneous formats: structured ERP JSON exports, native digital PDFs, multi-turn email correspondence, and degraded fax/photograph scans. 

A naive pipeline that pipes raw unredacted files into an expensive LLM fails on cost, privacy, latency, and determinism. Instead, this system implements an **intelligent document processing and human-review platform**:
1. **Deterministic by Default**: Known fields, commercial calculations (pack-to-unit conversions, volume discount tiers, MOQs), and previously approved schemas are executed deterministically in ordinary code.
2. **Schema Learning & Memory**: When an unfamiliar supplier schema arrives, the system proposes a mapping for human confirmation. Subsequent documents with the same normalized schema fingerprint are processed deterministically with **zero model calls, near-zero cost, and sub-second latency**.
3. **Preserve Source Truth vs. Derived Values**: Quoted commercial bases (e.g. `EUR 3.15 / pack`) are explicitly kept distinct from calculated values (e.g. `EUR 0.035 / tablet`).
4. **Uncertainty & Explicit Review Boundaries**: Missing or ambiguous fields remain explicit `null` values with review issues rather than hallucinated model guesses. Downstream systems accept offers only after human review decisions (`approved`, `rejected`, `corrected`).
5. **Strict Privacy Boundary**: All external model context is stripped of contact PII (emails, phone numbers, personal identifiers) via a deterministic redaction barrier before entering queues or worker contexts.
6. **Batch Progress & Failure Isolation**: Multi-file batch uploads derive aggregate progress from independent child document jobs; a corrupt or unsupported file fails safely without blocking or corrupting sibling documents.

---

## 1. System Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                        Vue 3 + Vite Review Desk                         │
│   - Multi-format file ingestion (JSON, EML, PDF, PNG, JPG)              │
│   - Batch progress tracker & aggregate status indicators               │
│   - Extracted offer review table with inline field-level corrections    │
│   - SSE EventSource consumer (Last-Event-ID reconnectable)              │
│   - Evaluation Lab (rubric scoring & benchmark execution)               │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ REST + SSE
┌────────────────────────────────────▼────────────────────────────────────┐
│                       FastAPI Application Layer                         │
│  app.api.application: Ingestion, Batch Orchestration, Review Workflow  │
└───────────────────┬─────────────────────────────────┬───────────────────┘
                    │                                 │
     (App State & Migrations)               (Enqueues Background Tasks)
                    ▼                                 ▼
┌────────────────────────────────────┐   ┌────────────────────────────────┐
│           data/app.db              │   │         data/tasks.db          │
│ SQLite WAL (Alembic Migrations)   │   │     SqliteHuey Queue Store     │
│  - batches                         │   └────────────────┬───────────────┘
│  - documents & document_artifacts  │                    │
│  - quotations & field_evidence     │                    ▼
│  - reviews & review_learning       │   ┌────────────────────────────────┐
│  - processing_events (SSE stream)  │   │       Huey Worker Loop         │
│  - schema_mappings & trust states  │   │  - Email extraction & revision │
│  - model_invocations               │   │  - Native PDF extraction       │
│  - evaluation_cases, runs, results │   │  - Degraded image OCR jobs     │
└────────────────────────────────────┘   │  - Correction schema learning  │
                                         └────────────────────────────────┘
```

### Layered Code Organization (`backend/app/`)
* **`api/`**: Fast HTTP routing, CORS configuration, SSE event streaming, and request lifecycle management.
* **`application/`**: Use cases including document ingestion, batch aggregation, human review commands, and evaluation execution.
* **`domain/`**: Pure business rules: `commercial_rules.py` (calculations, MOQ checks, validity dates), `schema_mapping.py` (fingerprinting and mapping engine), `pdf_parser.py` (pypdf signature & page quality verification), `email_parser.py` (MIME text extraction without HTML rendering), `image_parser.py`, and `ocr_contract.py`.
* **`infrastructure/`**: SQLAlchemy 2 models, database engines, and Alembic migration runners.
* **`workers/`**: Async Huey task consumers with bounded retries and explicit terminal state tracking.
* **`security/`**: Deterministic contact redaction (`redaction.py`).
* **`core/`**: Environment configuration and typed settings (`settings.py`).

---

## 2. Ingestion Paths by Document Modality

### A. Structured JSON (Sanova, Ubuntu, Zenith)
* The JSON structure is normalized and hashed into a canonical schema fingerprint: `(source_system, source_schema_version, normalized_shape_hash)`.
* **Cold Path**: Unfamiliar schemas receive a proposed mapping. When a reviewer confirms the mapping, it becomes `trusted`.
* **Warm Path**: The next upload with the same schema fingerprint applies the trusted mapping deterministically—making **0 LLM calls** and achieving 100% field parity with ground truth.
* If schema fields change unexpectedly, the system demotes the status to `needs_mapping_resolution` rather than blindly guessing.

### B. Supplier Email Threads (`.eml`, Novara RFQ)
* Native Python MIME parser extracts plain text bodies without rendering untrusted HTML or executing scripts.
* Sender contact details, telephone numbers, and email addresses are scrubbed.
* Queued to the semantic worker to detect chronological postscripts and price corrections (e.g. Azimax corrected in P.S. from EUR 0.128 to EUR 0.134/tablet).
* Audited model invocation records link duration and status to the extraction job.

### C. Native Digital PDFs (Farmaceutica Andina, Mekong)
* `pypdf` verifies PDF signatures and validates reading order.
* Evaluates native character density and text quality page-by-page.
* Clean digital pages bypass expensive OCR and queue to the structured semantic resolver.
* Degraded or unreadable pages selectively route to `needs_ocr`.

### D. Degraded Images & Scanned Faxes (Andina Scans)
* Validates image magic bytes and dimensions (PNG/JPEG).
* Governed by a typed, versioned OCR contract (`ocr_contract.py`) requiring bounding box coordinates, confidence scores, and DPI metadata.
* PaddleOCR service definition on Modal (`modal/ocr_service.py`) ready for deployment with authenticated API keys.

---

## 3. Commercial Rules & Ground Truth Fidelity

Commercial interpretation is strictly decoupled from raw string extraction:
* **Unit Price Derivation**: If a supplier quotes pack price and units per pack, unit price is derived deterministically:
  $$\text{unit\_price} = \frac{\text{pack\_price}}{\text{units\_per\_pack}}$$
  The raw pack price and derived unit price are preserved together with `derived: true` and the formula recorded in the canonical model.
* **MOQ Validation**: Checks whether quoted purchase quantities meet supplier minimum order restrictions.
* **Tiered Pricing**: Normalizes volume-based discounts and price adjustments.
* **Validity Dates**: Flags quotations that have expired or possess invalid date spans.

---

## 4. Batch Processing & Failure Isolation (Slice 8)

When an operator uploads a folder or multiple files at once:
* A `BatchRecord` is created, linking all child documents via `batch_id`.
* **Aggregate Metrics**: Total documents, status counts (`needs_review`, `needs_mapping_confirmation`, `failed`), and completion states are derived directly from child document rows—preventing out-of-sync counters.
* **Failure Isolation**: Each document is parsed inside an isolated try-catch block. If an individual file is corrupt (malformed JSON, broken PDF header, unsupported format):
  * The invalid file receives `status="failed"` and records its exact `failure_reason`.
  * Valid sibling documents continue processing, emit processing events, and enter review.
  * The whole batch is **never** aborted due to one bad file.

---

## 5. Security, Privacy & Compliance (Slice 9)

* **Presidio-Style Redaction**: Phone numbers and email addresses are replaced with `[redacted-phone]` and `[redacted-email]` tokens before payloads reach worker prompts, diagnostics, or database logs.
* **Seeded PII Audits**: Automated unit tests (`backend/tests/test_pii_audit.py`) verify that seeded personal contacts in email headers, nested dictionaries, and diagnostics endpoints never escape unredacted.
* **No Secret Leakage**: Database URLs, API tokens, and Modal service keys are injected via environment variables.

---

## 6. Continuous Integration & Test Strategy

* **GitHub Actions Workflow (`.github/workflows/ci.yml`)**:
  * Python 3.12 installation via `uv`.
  * Node.js 22 setup with NPM caching.
  * Backend linting (`ruff check backend`).
  * Backend automated test suite (50 tests covering commercial rules, migrations, schema learning, batch processing, PII audit, and worker task handling).
  * Frontend linting (`eslint . --max-warnings=0`).
  * Frontend unit/component tests (7 Vitest tests).
  * Frontend production build (`vue-tsc && vite build`).
  * Full browser end-to-end testing (Playwright E2E covering multi-file batch upload, mapping confirmation, price corrections, and approvals).

---

## 7. Operational Trade-offs & Production Roadmap

| Current Implementation | Production Evolution |
| :--- | :--- |
| **Local SQLite WAL (`app.db` / `tasks.db`)** | Managed PostgreSQL (Aurora/RDS) + separate Redis/RabbitMQ queue for horizontal multi-worker scaling. |
| **Local Filesystem Uploads (`data/uploads`)** | S3-compatible cloud storage (AWS S3 or Cloudflare R2) with presigned upload URLs. |
| **Local Huey Queue Worker** | Distributed Celery or Temporal workflow engine with dead-letter queues. |
| **Open Review Desk** | Role-Based Access Control (RBAC) with procurement auditor vs. reviewer roles and SSO. |
| **Modal OCR Escalation** | Direct deployment to Modal GPU endpoints with auto-scaling to zero during idle periods. |
