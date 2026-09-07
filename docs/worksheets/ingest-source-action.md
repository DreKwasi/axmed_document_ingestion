# Worksheet: ingest-source-action

> Purpose: durable handoff trace for the header ingest-action treatment.
> Status: in progress.
> Owner: frontend delivery.

## Goal and acceptance checks

- Home appears once as the main page title.
- Ingest source is visually a primary action button in the main page and remains keyboard-focusable.

## Context and constraints

This is a scoped Tailwind-only presentation change. Existing unrelated worktree changes remain untouched.

## Plan

1. Restyle the existing ingest trigger without changing its file-picker behavior.
2. Add a component-level regression assertion.
3. Run targeted validation and visually exercise the header.

## Work log and evidence

- 2026-09-07: Removed the redundant header route and page eyebrow. Home now appears only as the page title; the filled dark-green ingest action sits in the main page introduction and retains hover, focus-visible, and disabled states.

## Tests, app run, and validation

- 2026-09-07: `npm --prefix frontend test -- --run src/App.spec.ts` passed (8 tests).
- 2026-09-07: `npm --prefix frontend run build` passed.
- 2026-09-07: Local app at `http://127.0.0.1:5173` was refreshed and inspected: one Home heading, no header navigation, and the Ingest source button is in the main-page introduction.
- 2026-09-07: `bin/agent-validate full` passed: frontend lint, 8 component tests, production build, 2 Playwright journeys, Ruff, mypy, 76 backend tests, and 5 evaluation tests.

## Review findings and resolutions

- `bin/agent-review implementation` and `bin/agent-review wrap-up` found no independent provider configured. The locally completed checks cover behavior, UI hierarchy, accessibility states, and documentation consistency.

## Docs updated

- `docs/system/test-catalog.md` pending after test validation.

## Handoff / remaining work

No product behavior is intentionally left outstanding.

## Final commit and tag

Pending commit and `worksheet/ingest-source-action` tag.
