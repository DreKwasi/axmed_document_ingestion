# Worksheet: semantic-final-candidate-validation

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

Prevent a semantic extraction job from failing when the model returns a structured final candidate without calling the validation tool. The returned candidate must be deterministically validated before it can leave the agent, with its issues and telemetry preserved.

## Context and constraints

The PDF background task currently raises `ValueError` at `run_semantic_investigation` when `validation_count` is zero. The public semantic-agent seam owns deterministic validation; no provider output may bypass it.

## Plan

Add a red regression test for an unvalidated final candidate, then validate the final structured response after the model invocation and return a normal extraction result. Cover final-output validation even when the model did validate an earlier candidate.

## Work log and evidence

- 2026-09-09: Existing targeted test demonstrated the current failure contract; `bin/agent-validate targeted` passed before edits (122 backend tests).
- 2026-09-09: Research review could not dispatch an independent provider; isolated systems, security/domain, and quality passes are recorded below.
- 2026-09-09: Replaced the exception-only guard with a fingerprint check. The runner now invokes the same deterministic validation routine for a skipped or changed final structured candidate. A candidate that was already validated unchanged is not revalidated.

## Tests, app run, and validation

- Red loop: `env PYTHONPATH=backend uv run --project backend pytest backend/tests/test_semantic_agent.py -q` failed as expected before the code change: skipped validation raised `ValueError` and a changed final candidate was not counted as validated.
- Green loop: the same command passed, 15 tests.
- PDF processing regression scope: `env PYTHONPATH=backend uv run --project backend pytest backend/tests/test_pdf_parser.py -q` passed, 8 tests.
- App: started FastAPI on port 8017 and verified `/openapi.json` contains `/api/v1/documents`; then stopped the local server.
- `bin/agent-validate targeted` passed: frontend lint/tests, Ruff, mypy, and 123 backend tests.
- `bin/agent-validate full` passed frontend lint/tests/build, Ruff, mypy, 123 backend tests, and recorded evaluations (5 tests); its five Playwright E2E tests could not start because the pinned Chromium executable is absent. Added the environment repair to `TODOS.md`; this is unrelated to the change.

## Review findings and resolutions

- Systems: final structured output can differ from a candidate passed to the model tool; validate the returned output itself.
- Security/domain: retain deterministic commercial/provenance/completeness checks and do not persist output through this change.
- Quality: test both zero tool validations and a different final candidate after an earlier validation.
- Plan, implementation, and wrap-up review dispatches reported no independent provider configured. Isolated review found the change preserves app-owned validation, adds no external data exposure, and has focused red/green tests for both failure modes.

## Docs updated

- Updated `docs/system/test-catalog.md` for final structured-candidate validation coverage.

## Handoff / remaining work

The supplied document can be explicitly re-extracted after deployment. It will now proceed through deterministic validation rather than fail solely because the model omitted the tool call; ordinary provider or parsing failures remain surfaced normally.

`bin/agent-sweep` inspected the recent extraction-agent commits and completed without reporting a repository-specific warning. The only validation limitation is the separately queued missing Playwright browser runtime.

## Final commit and tag

- Code, tests, system-doc catalog, and feedback: `68100f1` (`fix(extraction): validate final semantic candidate`).
- This worksheet and its operational follow-up are committed and tagged `worksheet/semantic-final-candidate-validation` at wrap-up.
