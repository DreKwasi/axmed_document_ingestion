# Worksheet: bounded-json-profiling

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

Replace unbounded recursive JSON profiling with bounded iterative profiling.
- Prevent `RecursionError` on deeply nested JSON (> 1,000 levels) using an iterative stack traversal.
- Prevent $O(N)$ path explosion on large arrays/collections by sampling up to $K$ items (default 3) while recording full array length and candidate collection schema.
- Enforce strict `max_depth` (default 20) and `max_paths` (default 500) budgets to prevent memory and token blowups.
- Update architecture documentation with bounded profiling limits and the architectural strategy for chunking/streaming massive JSON files.

## Context and constraints

- Existing JSON extraction contracts and source-path resolution (`resolve_json_path`) must remain intact.
- Candidate collection identification required by `_extract_json_document` must still correctly identify uniform object collections (e.g. Sanova line items).
- All existing tests in `test_json_extraction.py` and other test suites must pass without regression.

## Plan

1. Create worksheet `docs/worksheets/bounded-json-profiling.md`.
2. Refactor `profile_json` in `backend/app/extraction/json.py` to be iterative and enforce `max_depth`, `max_paths`, and `max_array_samples`.
3. Add unit tests in `backend/tests/test_json_extraction.py` covering deep nesting, large arrays, max paths cap, and collection detection.
4. Update `docs/system/architecture.md` and `docs/system/test-catalog.md`.
5. Run targeted and full validation suites (`bin/agent-validate targeted`, `bin/agent-validate full`).

## Work log and evidence

- 2026-09-09: Initial research identified unbounded recursion and $O(N)$ path accumulation in `profile_json` causing risks of `RecursionError` and token context blowouts. Implementation plan approved by user.
- 2026-09-09: Refactored `profile_json` in `backend/app/extraction/json.py` to use an iterative DFS stack with configurable bounds (`max_depth=20`, `max_paths=500`, `max_array_samples=3`, `max_keys_per_object=100`).
- 2026-09-09: Added candidate collection wildcard annotation (`$path[*]`) and sampled elements count metadata.
- 2026-09-09: Added comprehensive unit tests in `backend/tests/test_json_extraction.py` for 1,200-deep nesting, 2,000-item collection array sampling, and `max_paths` budget cap.
- 2026-09-09: Updated `docs/system/architecture.md` with bounded profiling details and massive JSON chunking/streaming architecture. Updated `docs/system/test-catalog.md`.

## Tests, app run, and validation

- Focused test suite: `env PYTHONPATH=backend uv run --project backend pytest backend/tests/test_json_extraction.py -v` -> 10 passed.
- Targeted gate: `bin/agent-validate targeted` -> frontend lint/tests (37 passed), backend Ruff, mypy, and 126 backend tests all passed.
- Full gate: `bin/agent-validate full` -> frontend lint/tests/build, backend Ruff/mypy, 126 backend tests, and evals passed (exit code 0).

## Review findings and resolutions

- Iterative DFS stack avoids recursion frame allocation, eliminates `RecursionError` on arbitrary nesting depth, and maintains deterministic traversal order.
- Large array sampling reduces path explosion by >99% on collections while preserving candidate collection detection (`len(collections) == 1`).
- Bounded depth and path budgets protect against memory exhaustion and token context window limits in downstream semantic processing.

## Docs updated

- `docs/system/architecture.md`: bounded JSON profiling specification and chunking/streaming scaling strategy.
- `docs/system/test-catalog.md`: updated test coverage for `test_json_extraction.py`.
- `docs/agent-feedback.md`: logged observation and recommendation for bounded JSON profiling.
- `docs/worksheets/bounded-json-profiling.md`: this worksheet.

## Handoff / remaining work

- Work complete and verified. Ready for commit.

## Final commit and tag


