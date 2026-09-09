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

The semantic extraction tests cover the application-controlled extraction, grounding, validation, and investigation seams rather than private model reasoning. They prove that extraction cannot return evidence, grounding claims are checked against populated canonical fields and prepared-source references, JSONPath/value claims are resolved against the uploaded JSON, a failed grounding request enters the bounded investigation loop, all remaining ungrounded fields are sent together, and the hard run limit terminates the loop. Processor tests cover JSON persistence before background work, deterministic media routing, and commercial validation outside model calls. Live provider quality and interruption still require corpus evaluation.
