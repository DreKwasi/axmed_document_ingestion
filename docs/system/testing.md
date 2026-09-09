# Testing Strategy

> Purpose: define evidence required for safe changes and how tests are selected.
> Status: Slice 1 implemented — pytest/Ruff and Vitest/ESLint/Vite cover backend and frontend; Playwright arrives with the first browser E2E slice.
> Update when test layers, fixtures, commands, or test-writing guidance change.
> Owner persona: quality engineer.
> Related: `docs/system/test-catalog.md`, `docs/system/visual-regression.md`.
> Search terms: test, unit, integration, e2e, fixture, false confidence.
> Tests must validate observable behavior and be run at the narrowest useful scope first.

## Test pyramid and rules

- Unit tests cover deterministic domain logic and edge cases.
- Integration tests cover module boundaries, persistence, APIs, and real serialization.
- End-to-end tests cover user-critical journeys against a running app. Prefer stable accessible selectors and realistic state.
- Do not test private implementation details, unconditionally mocked success paths, or assertions that cannot fail when production behavior breaks.
- For every meaningful test addition/change, update `test-catalog.md` with its purpose, layer, and primary failure mode.
- Tests clear live provider credentials by default. A test that verifies provider configuration must set its required key explicitly with `monkeypatch`; no ordinary suite may make a billable or networked model call from a developer shell environment.

## Implementation loop

Reproduce the behavior, add a targeted assertion at the appropriate layer, make the change, run the focused test, then run the app. Before wrap-up run the appropriate broader suite through `bin/agent-validate full`.

## Semantic-investigation coverage

DI-17 tests the public agent and processor seams rather than private model reasoning. Current coverage proves that every result is submitted to deterministic validation, changed feedback can drive repeated investigation, repeated issue sets terminate as no progress, skipped validation is rejected, JSON source claims are value-checked, JSON is persisted before background semantic work, media routing remains deterministic, and commercial validation and human decisions stay outside the agent. Evidence-workspace tests cover stable JSON, PDF, and email references; whole-source versus retrieval selection; scoped search; composable inspection; and invalid evidence-reference issues. Tool, evidence-volume, and wall-clock limits are application-owned; live provider interruption and embedding-ranker quality still require dedicated evaluation coverage.
