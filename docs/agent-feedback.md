# Agent Feedback Log

> Purpose: concise operational feedback that improves this repository’s agent workflow.
> Add one entry at the end of each substantial session, even if no issue was found.
> Record the signal, impact, and proposed durable improvement; do not include chain-of-thought.
> Periodic sweeps cluster repeated feedback and update workflows, tools, or docs.
> Commit entries with their associated work so feedback remains historically connected.
> Keep this log actionable and remove superseded guidance only through a documented sweep.

| Date | Worksheet | Signal | Improvement | Status |
| --- | --- | --- | --- | --- |
| 2026-09-05 | bootstrap-agent-os | Empty repository has no runnable app or selected toolchain. | Add stack bootstrap task; validation scripts report this explicitly. | queued |
| 2026-09-06 | plan-document-intelligence | Infrastructure-first sequencing delayed the product’s schema-memory differentiator. | Require plans to demonstrate the riskiest product thesis in the earliest viable vertical slice. | adopted |
| 2026-09-06 | plan-document-intelligence | A prior OCR service's convenience HTTP response lost confidence and geometry needed for review evidence. | Treat provider services as adapters behind an explicit, versioned evidence contract. | adopted |
| 2026-09-06 | di-01-schema-learning-json | Curl-level success missed a browser origin mismatch and repeat-upload receipt collision. | Treat a real browser journey and repeated submission as required integration checks for every intake slice. | adopted |
| 2026-09-06 | di-02-commercial-review | A reviewer caught duplicate rules, permissive legacy baselining, and controls separated from their table context. | Require rule ownership, exact legacy signatures, and a browser layout check during review-slice wrap-up. | adopted |
| 2026-09-06 | di-03-durable-learning-sse | A retry queue can empty while its application record still looks pending, which hides exhausted failures. | Require every background task to persist an explicit terminal state and test it separately from queue delivery. | adopted |
| 2026-09-06 | di-08-batch-processing | In-memory or incremental batch counters drift on partial failure or worker restart. | Derive batch aggregate progress directly from database child document state with per-document failure isolation. | adopted |
| 2026-09-06 | di-10-langchain-gemini | Conflating decoupling with omitting LLM reasoning caused a pipeline gap. | Preserve the deterministic-first architecture (fast path, PII scrub, schema cache) while embedding LangChain + Gemini across all extraction sources with offline fallback. | adopted |
| 2026-09-06 | di-06-modal-ocr | Starting a worker before migrations lets stale queued work fail against a partial SQLite schema. | Run migrations before launching Huey and make historical interrupted migrations repairable when their prerequisite table is absent. | adopted |
