# Worksheet: clickable-filename-subtext

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks
- **Goal**: In the Source Table (`frontend/src/components/SourceTable.vue`), replace the separate "Download file" text and separator dot with directly clickable filename subtext.
- **Acceptance checks**:
  1. The "Download file" label and separator dot `·` are removed from the source rows under the Source column.
  2. The document filename is displayed as the interactive subtext link with `:href="sourceDocumentUrl(doc.id)"`, `:download="doc.filename"`, and `@click.stop`.
  3. Interactive cues include hover color shift to emerald (`text-slate-500 hover:text-emerald-700`), hover underline (`hover:underline`), cursor pointer, and title tooltip `Download ${doc.filename}`.
  4. Unit and E2E test suites (`App.spec.ts`, `batch.spec.ts`) are updated to reflect the new clickable subtext download behavior.
  5. Full validation (`bin/agent-validate full`) passes cleanly.

## Context and constraints
- Clicking anywhere on the row opens the source detail drawer. The subtext download link must prevent event propagation (`@click.stop`) so downloading does not accidentally open the drawer.
- The monospace styling (`font-mono text-[10px]`) and truncation (`truncate max-w-xs sm:max-w-md`) must be preserved to prevent layout shifts.

## Plan
1. Update `frontend/src/components/SourceTable.vue` to make `doc.filename` the download anchor tag directly.
2. Update unit tests in `frontend/src/App.spec.ts` and E2E tests in `frontend/e2e/batch.spec.ts`.
3. Fix TypeScript types in existing `App.spec.ts` tests for clean `vue-tsc` compilation.
4. Validate with `bin/agent-validate full`.
5. Document test catalog, worksheet, and feedback.

## Work log and evidence
- Replaced the separate `Download file` anchor and dot separator in `SourceTable.vue` with an interactive anchor containing `{{ doc.filename }}`.
- Updated `frontend/src/App.spec.ts` to assert that `andina.pdf`, `first.json`, and `second.json` are rendered as download links.
- Fixed TypeScript typing issue in `App.spec.ts` drawer test (`normalized_price` and string `minimum_remaining_shelf_life_percent`).
- Updated `frontend/e2e/batch.spec.ts` to check for the uploaded filename `sanova_offer_export_2026-08-03.json`.
- Ran `bin/agent-validate full` - all linting, unit tests, builds, E2E tests, and backend evals passed 100%.

## Tests, app run, and validation
- `npm --prefix frontend test`: 24 passed (24).
- `npm --prefix frontend run build`: 0 TypeScript or bundling errors.
- `npm --prefix frontend run test:e2e`: 2 passed (2).
- `bin/agent-validate full`: exited with 0 (frontend lint, vitest, build, playwright, backend ruff, mypy, pytest 93 passed, evals 5 passed).

## Review findings and resolutions
- Removed redundant visual clutter ("Download file ·") without losing the download affordance.
- Preserved keyboard accessibility with standard `<a>` element and download attributes.

## Docs updated
- `docs/system/test-catalog.md`: updated `App.spec.ts` description.
- `docs/agent-feedback.md`: logged observation on compact table link affordances.
- `docs/worksheets/clickable-filename-subtext.md`: created this record.

## Handoff / remaining work
- Ready to commit and present to user.
