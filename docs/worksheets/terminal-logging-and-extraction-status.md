# Worksheet: terminal-logging-and-extraction-status

> Purpose: durable handoff trace for one coherent change.

## Goal and acceptance checks

Make extraction lifecycle logs from all backend `app.*` modules visible in the FastAPI/Uvicorn terminal, and make a source awaiting model configuration visibly explain its state in the detail view.

## Context and constraints

- Do not commit changes; the user explicitly requested no automatic commits.
- Browser/Playwright tests are out of scope. Use focused backend and Vue component tests.
- Preserve persisted processing events as the client-safe activity source; terminal output is developer observability, not an API response.

## Plan

1. Configure one guarded console handler on the `app` logger namespace so child extraction and event loggers propagate to it.
2. Serialize embedded `awaiting` lifecycle stages as `Waiting`.
3. Render a stable waiting status card rather than treating it as ongoing extraction.
4. Run focused tests, targeted validation, and a manual Uvicorn upload reproduction.

## Work log and evidence

- 2026-09-09: Reproduced a two-page PDF upload with an empty model key. The persisted API events correctly reached `pdf_extraction_awaiting_model_configuration`, but the terminal omitted `app.events` and `app.extraction.pdf` INFO records.
- 2026-09-09: Confirmed `axmed.api` had the only console handler, while `app.events` and `app.extraction.pdf` inherited the root WARNING level. The UI regarded the serialized default `In progress` event as active work, then had no non-active empty state.
- 2026-09-09: Focused test exposed a second configuration edge: a framework logging reset can mark already-imported `app.*` children disabled. The shared configuration now explicitly re-enables that owned namespace.
- 2026-09-09: A real FastAPI lifespan check showed Alembic migration initialization was the reset point. Logger configuration is now intentionally bound after migrations, before startup completion and request/background processing.

## Tests, app run, and validation

- Focused tests: `uv run --project backend pytest backend/tests/test_processing_events.py -q` and `npm --prefix frontend test -- --run src/App.spec.ts` pass.
- Manual backend app run: an empty-key PDF upload through `TestClient(create_app())` returned `201` and printed API, event, PDF extraction, configuration-wait, and background-completion records to the terminal.
- Full validation initially surfaced an unrelated rejected-fixture type mismatch in `App.spec.ts`; aligned its `system_decision` with the current canonical type before rerunning.
- `bin/agent-validate targeted` passed: frontend lint/tests, Ruff, mypy, and 118 backend tests.
- `bin/agent-validate full` passed lint, unit/component tests, production frontend build, Ruff, mypy, 118 backend tests, and recorded evaluations. Its Playwright step could not launch because the local Chromium executable is absent; browser tests were explicitly out of scope for this session and no browser installation was performed.

## Review findings and resolutions

- No independent review provider is configured. Isolated systems/quality/code-quality/security/UX passes inspected the changed logger namespace, migration ordering, client-safe event phase, and waiting-state component branch. No unresolved correctness, data-exposure, or accessibility finding remains. The waiting card uses `role="status"` and does not claim extraction continues.

## Docs updated

- `docs/system/architecture.md`, `docs/system/test-catalog.md`, and `docs/agent-feedback.md` document the shared terminal logger behavior and coverage.

## Handoff / remaining work

- Restart the backend process to load the logging change. If the configured model key remains absent, the detail view will now explicitly say that configuration is required; configure the extraction service and re-extract to continue.
- Do not commit automatically; user instruction.

## Final commit and tag

Not created by user instruction.
