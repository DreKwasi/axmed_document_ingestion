# Worksheet: source-deletion

## Goal and acceptance checks

- Provide a visible delete action for every uploaded source.
- Require confirmation before deletion.
- Permanently remove the exact uploaded file and all records derived from that document.

## Context and constraints

- Deletion is intentionally destructive and explicitly requested by the user.
- The application uses SQLite without relying on database cascade rules for all document-scoped tables.

## Plan

- Add a `DELETE /api/v1/documents/{id}` endpoint and an application use case that removes dependents in foreign-key-safe order.
- Add the confirmation-gated source-table action and update client state after deletion.

## Work log and evidence

- Added the endpoint, client call, and source-table Delete action.
- File removal is limited to the stored upload basename inside the configured upload directory.

## Tests, app run, and validation

- Backend API regression: deletion returns `204`, and source/document retrieval returns `404` afterwards.
- Frontend component regression: confirmation invokes the API and removes the source from the table.
- Manual API smoke: temporary upload returned `204`; follow-up retrieval returned `404`.
- `bin/agent-validate full` completed frontend lint, tests, build, E2E, Ruff, mypy, and backend tests. A final direct backend run reported `92 passed, 1 warning`.

## Review findings and resolutions

- Do not delete a parent document before its model invocations, events, review learning, review commands, evidence, field values, normalized line-item children, and quotation rows.
- `agent-review` has no configured independent provider. Isolated systems, quality, and security passes found no unresolved dependency, test, or path-traversal gap. `agent-sweep` completed without warnings.

## Docs updated

- Architecture, test catalog, and feedback log.

## Handoff / remaining work

- No recoverability mechanism is provided: this is a permanent user-confirmed deletion.

## Final commit and tag

- Implemented by commits `e2ba579` and `9adcfe7`.
