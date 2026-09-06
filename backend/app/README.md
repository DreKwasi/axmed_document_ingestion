# Backend map

> Purpose: navigate the FastAPI backend by responsibility instead of root-level file name.
> Entry point: `app.api.application` composes HTTP routes, configuration, database, and workers.
> `application/` holds use cases: document intake/review, evaluations, and processing events.
> `domain/` holds canonical contracts and deterministic commercial, schema, and email interpretation.
> `infrastructure/` holds SQLite/Alembic-facing database and ORM modules.
> `workers/` holds Huey task definitions, durable document processing, OCR/service adapters, and long-running learning execution.
> `security/` holds privacy/redaction adapters; `core/` holds configuration.

## Import rule

There are no root-level implementation modules. Import directly from the owning package: for example `app.workers.ocr` runs the durable OCR job, while `app.workers.ocr_client` owns the narrowly scoped HTTP call to the external service.
