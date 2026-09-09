# Worksheet: submission-agent-conversation

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

- Replace the stale agent-conversation narrative with an agent-generated summary of the current system and the candidate's decision-making role.
- Remove the unrelated `WRITEUP.md` and its repository references.
- Preserve the submission's actual implementation facts: one FastAPI + Vue application, API-owned background work, per-document semantic extraction, deterministic commercial validation, evidence grounding, confidence, and human review.

## Context and constraints

- The submission asks for an LLM/Claude-generated Markdown summary of the planning/execution conversation that highlights the candidate's guidance.
- `AGENT_CONVERSATION.md` currently describes retired schema-learning, Huey, batch, and Modal-deployment behavior. `docs/system/architecture.md` and current tests document the replacement architecture.
- The worktree contains unrelated in-progress changes. This change will touch only the requested submission documents and documentation trail.

## Plan

1. Inspect the current backend routes, processing pipeline, frontend, tests, and architecture documentation.
2. Rewrite `AGENT_CONVERSATION.md` around verified current behavior and clearly distinguish the candidate's decisions from agent implementation support.
3. Delete `WRITEUP.md`, remove its README references, and record validation/review evidence.

## Work log and evidence

- 2026-09-09: Read `AGENTS.md`, `AGENT_WORKFLOW.md`, task queue, coding conventions, architecture, testing guidance, and worksheet template.
- 2026-09-09: Inspected public API routes in `backend/app/api.py`, backend test suite, current source tree, and recent commits. Confirmed `POST /api/v1/documents` supports multi-file uploads; API-owned background processing, SSE, CSV export, source deletion, re-extraction, image-attempt review, and human review endpoints are current.
- 2026-09-09: Research and plan review commands reported that no independent provider is configured; isolated systems, security, and quality persona passes will be recorded before handoff.
- 2026-09-09: Read the historical DI-01 through DI-10 and DI-17/orchestration worksheets. They establish that schema mapping reuse, Huey, persisted batches, and model-selected agent loops were historical slices later superseded by the current application-controlled design.
- 2026-09-09: Replaced `AGENT_CONVERSATION.md` with a submission-facing, agent-generated summary grounded in the current code and the worksheet trail. It distinguishes historical experiments from the implementation that remains.
- 2026-09-09: Replaced the simplified submission pipeline with the complete code-backed architecture and investigation-loop diagrams: source-specific preparation, `EvidenceWorkspace`, primary extraction, deterministic validation, full grounding, claim validation, the three-run/no-progress evidence loop, persistence, and human review.
- 2026-09-09: Corrected the submission summary to state that the candidate wrote and integrated the application code, using the agent for planning, research, debugging, and review. It now credits the candidate's active manual course corrections when agent-assisted approaches drifted or overcomplicated the architecture.
- 2026-09-09: Updated the README to replace stale LangChain-agent/OpenRouter/batch wording with the active FastAPI and Vue architecture: API-owned background work, source-specific preparation, application-controlled extraction/grounding/investigation, evidence validation, dual confidence, human review, and Google-only provider configuration.
- 2026-09-09: Added code-backed README confidence methodology from `backend/app/extraction/confidence.py`: weighted extraction-recovery formula, OCR legibility calculation, deterministic per-field mapping tiers, commercial-consistency bonus, aggregate mapping formula, issue semantics, score bands, and review routing.
- 2026-09-09: Added the same code-backed confidence methodology to `AGENT_CONVERSATION.md` so the required agent-generated submission summary explains the calculations and the candidate's requirement for evidence-derived confidence.
- 2026-09-09: Removed `WRITEUP.md` at the user's request and removed its README link/tree entry. No code or runtime behavior changed.

## Tests, app run, and validation

- `bin/agent-validate targeted` passed: frontend ESLint and 38 Vitest tests, backend Ruff, Mypy, and 129 Pytest tests passed.
- The FastAPI application started with `uv run uvicorn main:app --host 127.0.0.1 --port 8020` from `backend/`; `GET /health` returned `{"status":"ok","service":"axmed-document-intelligence"}`. The temporary server was stopped after the check.
- `bin/agent-validate full` passed lint, frontend tests/build, backend Ruff/Mypy/Pytest (129 passed), and evaluation tests (3 passed). Its five Playwright journeys could not launch because the local Playwright Chromium executable is absent; this is an environment prerequisite, not a documentation-change failure.

## Review findings and resolutions

- Research, plan, and wrap-up review dispatchers found no configured independent provider.
- Isolated systems review confirmed the replacement describes current code and labels retired worksheet behavior as historical. Security review confirmed no source/provider behavior changed. Quality review confirmed `WRITEUP.md` references were removed from active README, task-queue, plan, and PRD documentation; historical worksheets retain their factual delivery record.

## Docs updated

- `AGENT_CONVERSATION.md`, `README.md`, `TODOS.md`, the implementation plan, the PRD tree, and this worksheet. Removed `WRITEUP.md`.

## Handoff / remaining work

- The only outstanding validation prerequisite is `npx playwright install` (or an equivalent managed browser installation) before browser E2E can run. No code change is required for this documentation cleanup.

## Final commit and tag

- Pending. Do not commit or tag without explicit user instruction.
