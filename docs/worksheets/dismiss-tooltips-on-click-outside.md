# Worksheet: dismiss-tooltips-on-click-outside

> Purpose: durable handoff trace for dismissing tooltips on click-outside, Escape key, or navigation transitions.
> Finalize with the associated commit and `worksheet/dismiss-tooltips-on-click-outside` tag when Git is available.

## Goal and acceptance checks

- [x] Clicking outside any open tooltip or explanation popover immediately closes it.
- [x] Pressing the `Escape` key closes any active tooltip.
- [x] Selecting a product row in `ProductTable.vue` dismisses open table-level tooltips so they do not linger over `ProductDetailDrawer.vue`.
- [x] Selecting a source row in `SourceTable.vue` dismisses open mapping tooltips.
- [x] Product detail drawer mapping concern banners provide an explicit dismiss affordance and dismiss on outside clicks or Escape.
- [x] Automated test in `frontend/src/App.spec.ts` protects tooltip dismissal on click-outside, Escape, and drawer transitions.
- [x] All targeted validations (`lint`, `test`, `backend`) pass with zero errors.

## Context and constraints

- User reported: "Tooltips dont close when i click something else", accompanied by a screenshot showing the "How mapping confidence is built" tooltip floating over the product detail drawer.
- The previous tooltip implementation relied strictly on `@click.stop` toggle handlers without document-level click-outside or keyboard listeners.
- Opening the drawer via row click also did not reset table-level tooltip visibility, allowing table popovers with high z-index to overlay the drawer.

## Plan

1. In `ProductTable.vue`, add document click-outside and `Escape` listeners with `data-tooltip-container` boundary detection; dismiss table tooltips on row select before emitting `selectLine`.
2. In `ProductDetailDrawer.vue`, add document click-outside and `Escape` listeners, dismiss tooltips when watching drawer/lineItem/field changes, and add an explicit close button on the mapping concern explanation banner.
3. In `SourceTable.vue`, add document click-outside and `Escape` listeners, and dismiss tooltips on row select.
4. Add comprehensive Vitest tests in `frontend/src/App.spec.ts`.
5. Run full targeted validations via `bin/agent-validate targeted`.

## Work log and evidence

- Updated `frontend/src/components/ProductTable.vue`:
  - Added `data-tooltip-container` attribute to header mapping confidence and row mapping confidence buttons.
  - Implemented `closeTooltips()`, `toggleMappingDefinition()`, `toggleMappingTooltip(index)`.
  - Added safe `handleDocumentClick` (checking `target.closest?.("[data-tooltip-container]")`) and `handleDocumentKeydown` for `Escape`.
  - Added `closeTooltips()` to `@click` on product row before emitting `selectLine`.
- Updated `frontend/src/components/ProductDetailDrawer.vue`:
  - Added document click and `Escape` listeners.
  - Added `data-tooltip-container` on explanation popover buttons and banner.
  - Added explicit close button (`✕`) on `showMappingConcernDefinition` banner.
  - Reset tooltips on drawer close or selection change.
- Updated `frontend/src/components/SourceTable.vue`:
  - Added document click and `Escape` listeners.
  - Added `data-tooltip-container` attribute.
  - Dismissed tooltips on row click.
- Fixed `SourceDetailHeader.vue`:
  - Added safe optional chaining for `document.quotation?.commercial_terms?.currency` to prevent runtime TypeErrors when commercial terms are empty.
- Updated `frontend/src/App.spec.ts`:
  - Added assertions for table tooltip dismissal upon opening product drawer.
  - Added dedicated test `closes tooltips when clicking outside, pressing Escape, or navigating`.

## Tests, app run, and validation

- `npm --prefix frontend run lint`: 0 errors, 0 warnings.
- `npm --prefix frontend test`: 22 passed across 2 test files.
- `bin/agent-validate targeted`:
  - Frontend lint: passed (max-warnings=0)
  - Frontend test: 22 passed (Vitest)
  - Backend ruff: All checks passed!
  - Backend mypy: Success: no issues found in 26 source files
  - Backend pytest: 92 passed, 1 warning (deprecation from starlette testclient)

## Review findings and resolutions

- `target.closest` is not a function when clicking directly on `Document` root in JSDOM/DOM: Resolved by using optional chaining `target.closest?.("[data-tooltip-container]")` and typing `target as Element | null`.

## Docs updated

- `docs/system/test-catalog.md`: Updated `frontend/src/App.spec.ts` entry with tooltip dismissal coverage.
- `docs/agent-feedback.md`: Added entry for `dismiss-tooltips-on-click-outside`.
