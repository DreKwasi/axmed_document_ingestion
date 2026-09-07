# Backend code map

> Purpose: make each backend location obvious from its name.
> Entry point: `app.api` creates FastAPI and contains every public route.
> `documents.py` owns document intake, persistence, serialization, re-extraction, and review operations.
> `extraction/` owns parsing, semantic extraction, normalization, confidence, and provider adapters.
> `models.py` defines persisted records; `database.py` configures SQLAlchemy and Alembic.
> `events.py` owns persisted processing activity; `evaluations.py` is called only by developer tooling.
> `security/` owns privacy and redaction behavior.

## Files

```text
app/
├── api.py                 # FastAPI setup and all HTTP routes
├── config.py              # Environment-backed settings
├── database.py            # SQLAlchemy engine/session and migrations
├── documents.py           # Document and review operations
├── events.py              # Safe persisted processing events
├── evaluations.py         # Offline/developer evaluation operations
├── logging.py             # API logging setup
├── models.py              # SQLAlchemy records
├── extraction/
│   ├── contracts.py       # Canonical quotation models
│   ├── confidence.py      # Extraction confidence and review reasons
│   ├── commercial.py      # Commercial validation and derivation
│   ├── json.py            # JSON profiling, fact extraction, and JSONPath checks
│   ├── llm.py             # LangChain/Gemini structured extraction
│   ├── email_*.py         # Email parsing, reconciliation, and processing
│   ├── pdf_*.py           # PDF parsing and processing
│   └── image_*.py         # Image validation and OCR processing
└── security/
    └── redaction.py       # Contact PII redaction
```

The name `processing` means an in-process extraction function. There is no queue worker runtime or `workers/` package.
