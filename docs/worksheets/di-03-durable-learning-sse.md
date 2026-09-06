# Worksheet: DI-03 durable learning and SSE

> Purpose: durable handoff trace for background correction learning and reconnectable progress.
> Scope: use a separate SQLite-backed Huey queue, persist safe events, and stream them from the API.
> Status: active implementation; durable events, dispatch, and resolver boundary are in place.
> Dependencies: DI-02 at `worksheet/di-02-commercial-review`.
> Source requirements: PRD v2 and Slice 3 in `docs/plans/implementation-plan.md`.
> Privacy rule: model-facing learning context is redacted; events, diagnostics, and failures never contain raw document text or contact PII.
> No Modal deployment is involved.

## Goal and acceptance checks

- A correction-learning record is consumed by a separate local Huey worker after redaction.
- Ordered safe events can be replayed with SSE `Last-Event-ID` without duplicating a terminal state.
- Retry is explicit, bounded, and idempotent; duration is recorded for local diagnostics.

## Research notes

- DI-02 writes one queued `review_learning` row per corrected review and deliberately does not run a model.
- The API and worker must use separate SQLite files; application events remain in `app.db` as the browser/worker boundary.

## Plan

1. Add a small queue/worker port with `SqliteHuey`, settings for a distinct queue DB, and migration-backed processing-event/invocation records.
2. Red-test event persistence, Last-Event-ID replay, redaction, worker idempotency, and bounded retry before wiring the worker.
3. Add a concise activity indicator only if it improves the existing table; diagnostics remain an API/report seam first.

## Work log and evidence

- 2026-09-06: DI-02 committed at `0c1ecce`; began Slice 3 orientation against the PRD, plan, architecture, testing, and conventions docs.
- 2026-09-06: Added a separate `SqliteHuey` queue, safe persisted processing events, reconnectable SSE, and invocation records through Alembic revision `20260906_03`.
- 2026-09-06: Correction dispatch occurs only after its review transaction commits. The worker redacts context, calls an operator-configured resolver contract, stores only field preferences, demotes the old trusted mapping to a proposal, and requires human confirmation before reuse.
- 2026-09-06: No resolver URL is configured locally, so the worker records `awaiting_model_configuration` rather than claiming an LLM ran.
- 2026-09-06: Implementation persona review found that a retrying task could look permanently queued after Huey exhausted its two retries. The worker now records a safe terminal `failed` transition; each Huey retry explicitly moves it back to `running`.
- 2026-09-06: Added a safe local diagnostics endpoint with event-stage counts and model-invocation duration/status metadata. It deliberately excludes document content, review values, and error internals.

## Review, tests, and validation

- Focused Ruff and 15 backend tests passed: events/SSE cursor validation, corrections, migration, and mocked resolver execution/redaction/preference persistence.
- Local personas: quality checked correction/retry/event paths; code quality checked the worker boundary and idempotent invocation upsert; security checked resolver/event payloads for PII and raw-text leakage; UX confirmed the review page remains table-first and the empty state is now just `No documents.`. The external review wrapper has no configured provider.
- Isolated `bin/dev` smoke: API, Vue, and Huey ran against temporary separate `app.db`/`tasks.db`; a correction yielded ordered `learning_queued`, `learning_started`, and `learning_awaiting_model_configuration` events.
- Remaining: add a direct SSE replay transport test, improve operational diagnostics presentation only if it stays compact, full revalidation after remaining Slice 3 changes, independent review if an external provider is configured, and user-authorized commit/tag.

## Handoff / remaining work

Continue Slice 3 with runtime worker smoke coverage, diagnostics, retry/replay coverage, and UI activity evidence. Do not commit or tag unless the user changes the explicit no-commit instruction.
