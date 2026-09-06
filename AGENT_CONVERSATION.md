# Agent Planning and Execution Summary (AGENT_CONVERSATION.md)

> **Context:** Axmed Supplier Document Intelligence Take-Home  
> **Purpose:** Detailed summary of the AI-agent conversation, planning process, and execution trajectory, highlighting the candidate's guidance, architectural leadership, and strict verification standards.

---

## 1. Candidate's Role and Architectural Direction

Throughout the development of this repository, the candidate operated as the **system architect and engineering lead**, steering the AI coding assistant with rigorous constraints:

1. **Rejecting Naive "LLM-on-Everything" Approaches**:
   - The candidate mandated that deterministic data, mathematical derivations (pack-to-unit conversions, volume discount tiers), and previously verified supplier schemas must be handled with pure software and zero model invocations.
   - The primary differentiator—**Schema-Learning Memory**—was placed front-and-center: unfamiliar schemas are confirmed once by a human; subsequent encounters of the same normalized schema fingerprint are processed deterministically with **zero LLM calls**, zero token cost, and sub-second latency.

2. **Enforcing a Disciplined Agent Operating System (`AGENTS.md`)**:
   - Instead of unstructured ad-hoc code edits, the candidate enforced an automated harness:
     - **`AGENTS.md` & `AGENT_WORKFLOW.md`**: Strict loop (*Orient &rarr; Research &rarr; Plan &rarr; TDD Implement & Verify &rarr; Harden &rarr; Wrap Up*).
     - **`TODOS.md`**: Local single-source-of-truth task queue with explicit readiness and dependency gates.
     - **Worksheets (`docs/worksheets/`)**: Persistent evidence records documenting exact commands, outputs, failure modes, and handoff criteria.
     - **`docs/system/`**: 10 system documents with greppable 7-line summaries kept synchronized with code changes.
     - **Validation Automation (`bin/agent-validate full`)**: Zero tolerance for broken linters, failing tests, or mocked-only assertions.

3. **Demanding Failure Isolation and Reliable Boundaries**:
   - For batch processing (Slice 8), the candidate required that corrupt or invalid files fail independently with clear reasons, while valid siblings continue through the pipeline without disruption.
   - For background processing (Slice 3), the candidate ensured separate SQLite files for application state (`app.db`) and Huey tasks (`tasks.db`) to prevent database lock contention, accompanied by reconnectable SSE streams via `Last-Event-ID`.
   - For security and compliance, the candidate required deterministic PII scrubbing of contact information before any data leaves local boundaries.

---

## 2. Chronological Trajectory of Slices

### Slice 1 — Schema-Learning JSON Vertical Slice (DI-01)
* **Goal**: Establish the core technical thesis with minimal infrastructure.
* **Agent Action**: Built FastAPI ingestion, canonical quotation Pydantic model, SHA-256 schema fingerprinting, human mapping confirmation, and version-scoped cache reuse.
* **Candidate Review & Pivot**: The candidate caught that repeat uploads of the same file caused database primary key collisions and that curl-based testing missed CORS/browser origin handling. The agent adjusted document identity to random UUID receipts while tracking SHA-256 for content identity, and added browser component testing.

### Slice 2 — Commercial Rules & Review Desk (DI-02)
* **Goal**: Implement deterministic domain validation, pack-to-unit derivation, and reviewer decision workflows.
* **Agent Action**: Created pure domain service `commercial_rules.py` (`validate_and_derive`), MOQ checks, and revision-tracked review decisions (`approved`, `rejected`, `corrected`).
* **Candidate Review & Pivot**: The candidate directed that commercial rules must never contain supplier aliases (which belong strictly in schema mapping), and required that review controls remain embedded directly in the quotation table context for UX ergonomics.

### Slice 3 — Durable Background Queue & SSE (DI-03)
* **Goal**: Add async worker processing and real-time browser progress streaming.
* **Agent Action**: Integrated `SqliteHuey` queue with dedicated `data/tasks.db`, monotonic `processing_events` table, and SSE streaming with `Last-Event-ID` cursor replay.
* **Candidate Review & Pivot**: The candidate observed that when background retries are exhausted, tasks could look permanently queued. The agent introduced an explicit terminal `failed` state and verified worker retry idempotency.

### Slice 4 & 5 — Multi-Format Intake: Email & Native PDF (DI-04, DI-05)
* **Goal**: Expand ingestion beyond JSON to supplier emails and digital PDFs.
* **Agent Action**:
  - Built `email_parser.py` using Python's native MIME library to extract plain text without rendering untrusted HTML or executing scripts, handling Novara RFQ postscript price supersessions.
  - Built `pdf_parser.py` using `pypdf` with page-level text density heuristics to route clean digital pages to semantic extraction and degraded pages to OCR.
* **Candidate Review & Pivot**: The candidate insisted on refactoring the backend into a clean layered architecture (`api/`, `application/`, `domain/`, `infrastructure/`, `workers/`, `security/`, `core/`), documented in `backend/app/README.md`.

### Slice 6 — OCR Escalation & Modal Adapter (DI-06)
* **Goal**: Prepare image parsing and degraded scan OCR escalation.
* **Agent Action**: Defined `ocr_contract.py` with bounding boxes, confidence, and DPI requirements. Built PaddleOCR service for Modal (`modal/ocr_service.py`) and a local client adapter with image signature verification.
* **Candidate Review & Pivot**: In accordance with cost controls, live deployment to Modal was guarded by explicit operator authorization, while 100% of the local contracts, queue lifecycles, and mock tests were validated.

### Slice 8 — Independent Batch Progress & Failure Isolation (DI-08)
* **Goal**: Allow folder or multi-file uploads with independent processing and failure isolation.
* **Agent Action**: Added `batches` table via Alembic revision `20260906_10`, `create_batch`, and `POST /api/v1/batches`. If one file is corrupt (e.g. malformed JSON or invalid file format), it receives an isolated `failed` status with its specific error message, while valid siblings process and enter review.
* **Candidate Review & Pivot**: Directed that batch aggregates (counts of documents, status breakdown) must be derived dynamically from child document rows rather than maintained as mutable counters that could drift on crash.

### Slice 9 — Delivery Hardening, CI & Submission (DI-09)
* **Goal**: Continuous integration, automated PII audits, and comprehensive documentation.
* **Agent Action**:
  - Created `.github/workflows/ci.yml` running linting, unit/integration testing, frontend build, and Playwright browser smoke tests.
  - Built automated seeded-PII audit suite in `backend/tests/test_pii_audit.py`.
  - Authored `WRITEUP.md`, updated `README.md`, updated system docs (`architecture.md`, `test-catalog.md`), finalized worksheets, and updated `TODOS.md`.
* **Validation Outcome**: 100% pass across all checks (50 Pytest tests, 7 Vitest tests, 2 Playwright E2E browser journeys, zero lint warnings).

---

## 3. Summary of Interaction Principles

- **Pragmatic Pair Programming**: The candidate served as the domain expert, reviewer, and guardian of engineering standards; the agent operated as the rapid implementation engine and test generator.
- **Evidence Over Assertions**: No feature was declared done without running the actual application and automated validations (`bin/agent-validate full`).
- **Clean Architecture Over Premature Complexity**: Kept the stack lean, reliable, and easily deployable without unnecessary frameworks (e.g. no LangGraph, no external Redis requirement, no unneeded microservices).
