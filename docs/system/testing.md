# Testing Strategy

> Purpose: define evidence required for safe changes and how tests are selected.
> Status: bootstrap — choose the concrete test runner with the application stack.
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

## Implementation loop

Reproduce the behavior, add a targeted assertion at the appropriate layer, make the change, run the focused test, then run the app. Before wrap-up run the appropriate broader suite through `bin/agent-validate full`.
