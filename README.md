# Axmed Supplier Document Intelligence

> Intelligent multi-format quotation extraction and human-review pipeline for pharmaceutical procurement.

- 🌐 **Live Platform (Cloudflare Pages)**: [https://axmed-document-ingestion.pages.dev/](https://axmed-document-ingestion.pages.dev/)
- 🚀 **Live Backend API (Railway)**: [https://axmeddocumentingestion-production.up.railway.app](https://axmeddocumentingestion-production.up.railway.app) *(Docs: [/docs](https://axmeddocumentingestion-production.up.railway.app/docs))*

---

## Overview

Axmed receives supplier quotations in varied formats: structured JSON exports, native digital PDFs, multi-turn emails with price corrections, and degraded image scans. This platform extracts, normalizes, validates, and presents supplier offers for human review.

Key capabilities:

- **Per-document, source-grounded extraction**: JSON is interpreted independently; direct JSON claims retain their exact JSONPath and value. Uncertain normalization is stored as an unmapped fact rather than becoming a reusable supplier rule.
- **Application-controlled semantic investigation**: Python controls extraction, grounding, claim validation, retries, and termination. Gemini is used for bounded semantic interpretation only; it cannot route files, persist unvalidated evidence, calculate commercial values, or approve a quotation.
- **Independent multi-file intake**: A single upload can contain multiple files. Each becomes an independent source record, so an invalid sibling fails without blocking usable documents.
- **Evidence-led review**: The review desk exposes source material, normalized products, field provenance, extraction confidence, mapping confidence, and actionable mapping issues before a reviewer approves, rejects, or corrects a source.
- **Deterministic commercial validation**: Unit-price derivation, MOQ checks, volume tiers, and date validation run in Python and keep derived values distinct from supplier-stated values.
- **Safe background processing**: API-owned bounded workers persist progress events and replay them through reconnectable Server-Sent Events (SSE).
- **Privacy-aware preparation**: Email contact details are redacted before semantic processing and logs contain only safe operational metadata. Images retain an explicit external-provider privacy boundary because their pixels cannot be safely text-redacted.

## Architecture

```text
JSON / EML / PDF / PNG-JPEG
          │
          ▼
FastAPI intake: media validation, generated storage name, independent source record
          │
          ▼
API-owned background executor ──► persisted, reconnectable SSE processing events
          │
          ├── JSON: bounded structural profile + JSONPaths
          ├── EML: MIME parsing, chronology, contact redaction
          ├── PDF: LiteParse reading order and layout-aware pages
          └── Image: PaddleOCR-assisted and direct-vision peer attempts
          │
          ▼
EvidenceWorkspace: addressable source context
          │
          ▼
Application-controlled extraction → grounding → bounded evidence investigation
          │
          ▼
Commercial rules + provenance + dual confidence → human review → Vue workspace / CSV
```

### Semantic extraction and grounding loop

The application controls every transition. The model receives a prepared source and returns structured data; it does not choose tools or determine whether the workflow continues.

```text
1. Build EvidenceWorkspace from prepared source material.
2. Primary extraction returns canonical quotation values and a reviewer narrative.
3. Python validates completeness and deterministic commercial rules.
4. Full grounding returns field-specific canonical-field / source-value / source-reference claims.
5. Python accepts a claim only when the field exists, the reference resolves, the cited source contains the value,
   and direct values (including JSONPaths) agree with the canonical candidate.
6. Missing or invalid support enters an evidence-only investigation loop. It receives every unresolved field and
   rejected claim, may return new evidence claims only, and stops after no progress or three runs.
7. Persist the candidate, valid evidence, source facts, confidence, and remaining review issues.
```

`extraction_confidence` measures source recovery; `mapping_confidence` measures whether recovered values were assigned to the correct canonical fields. They are separate signals. A reviewer remains the authority for approval or rejection.

## Confidence model

Confidence is calculated from observable source and evidence signals—not from a model self-rating. The system keeps two independent scores because a document can be easy to read but ambiguously mapped, or difficult to read but have a well-grounded field assignment.

### Extraction confidence: source-recovery quality

This is a document-level score calculated after preparation:

```text
extraction_confidence = round(
    0.30 × machine_readability
  + 0.25 × parser_quality
  + 0.45 × text_legibility
)
```

| Factor | Weight | How it is scored |
| --- | ---: | --- |
| Machine readability | 30% | 100 for JSON, email text, and native-text PDFs; 40 when OCR is required; 70 for another readable but unstructured source. |
| Parser quality | 25% | `good` 100, `mixed` 70, `poor` 40, `failed` 0; an unreported parser warning defaults to 85. |
| Text legibility | 45% | 100 when OCR is unnecessary. With OCR, it is the average of mean OCR line confidence and the percentage of lines at or above 0.80 confidence. |

Scores are banded as **High** at 85–100, **Medium** at 65–84, and **Low** below 65. A source with no extracted result has no extraction-confidence score. Low OCR quality remains visible for review; it does not silently discard a potentially useful source.

### Mapping confidence: source-to-schema certainty

This score is calculated for every populated canonical field from its persisted evidence. It answers a different question: *does this source value belong in this canonical field?*

| Evidence condition | Field score | Meaning |
| --- | ---: | --- |
| Direct JSON mapping or a human correction | 100 | The source explicitly identifies the value as that field. |
| Addressable row, column, or cell | 92 | The value is pinned to structured table context. |
| Source path or source location | 82 | The value is grounded in the source, but the source does not explicitly name the canonical field. |
| Evidence without an exact location | 70 | The value was extracted, but the precise source location was not recorded. |
| Category mismatch or conflicting validation | 30 | The source-to-field association contradicts evidence or commercial validation. |
| No source-linked evidence | 0 | The field is recorded as missing mapping evidence and becomes an actionable issue. |

For affected commercial fields, a successful mathematical cross-check adds 5 points (capped at 100):

```text
quoted_quantity × quoted_unit_price × (1 − discount) = extended_price
quoted_unit_price × units_per_pack = pack_price
```

The overall mapping score is the rounded arithmetic mean of all populated field scores:

```text
mapping_confidence = round(sum(field_scores) / number_of_populated_fields)
```

Mapping issues are not simply fields below 100. They identify missing evidence, contradictions, ambiguities, or invalid mappings. For example, a grounded email field can score 82 with no mapping issue: it is supported by source text but lacks the explicit schema label available in a structured JSON export.

### Review routing

The scores support review; they do not replace it. `pre_approved` requires 100 extraction confidence, 100 mapping confidence, and no mapping issues. Any other usable quotation is `pending_review`, where a reviewer can inspect evidence, correct values, approve, or reject. A zero-product extraction is recorded as failed while retaining validated source facts for inspection.

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
# Optional for live semantic extraction: add GEMINI_API_KEY in backend/.env.
# Google Gemini 3.5 Flash Lite is the sole code-owned semantic provider.
# The token for the OCR service (OCR_SERVICE_TOKEN) is available in the Google Docs appendix section of the architecture.

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
│   ├── src/                 # Vue 3 review workspace
│   └── e2e/                 # Playwright end-to-end smoke tests
├── docs/
│   ├── system/              # Architecture, testing, conventions system docs
│   ├── worksheets/          # Implementation worksheets & session evidence
│   └── product/             # Product Requirements Document (PRD)
├── sample_documents/        # Synthetic supplier fixtures (JSON, EML, PDF, PNG, JPG)
├── backend/evals/           # Golden datasets, outputs, recorded extraction fixtures, and OCR fixtures
└── AGENT_CONVERSATION.md    # Agent-generated planning and execution summary
```
