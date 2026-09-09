# Worksheet: review-status-and-unclear-scan-ux

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

- [x] Eliminate the false-positive 409 error banner ("This image extraction result is not available for review") caused by the watcher auto-selecting failed image attempts.
- [x] Present "Extraction failed" as a first-class document state rather than an alarming warning or error banner, removing the yellow/amber alert banner from above the header.
- [x] Integrate extraction state details inside the document header card without alert styling (`bg-surface-alt border border-rule`).
- [x] Omit the empty 4-column quotation metadata strip (`Supplier`, `Delivery Terms`, etc.) when `document.quotation` does not exist.
- [x] Update review status presentation so that after a user reviews, the status clearly updates to "Approved" (green badge/indicator) or "Rejected" (red badge/indicator) instead of generic "Ready".
- [x] Add a prominent, responsive Toast notification system that alerts the user when a review decision ("Approved" or "Rejected") or field correction is successfully submitted.
- [x] Verify with targeted automated tests (`bin/agent-validate targeted`).
- [x] Present the review lifecycle as Pre-approved, Needs review, Approved, or Extraction failed with flat semantic colors.
- [x] Replace the text delete action with an accessible trash icon.
- [x] Preview PDF, image, JSON, email, and browser-readable source files in-platform from both Home and source detail.
- [x] Merge mapping issue counts into mapping-confidence subtext and remove tinted confidence/count pills.
- [x] Refine Home source typography for a calmer, less heavy hierarchy.
- [x] Reduce the product drawer to a neutral palette, reserving purple for the save action and one muted amber accent for review concerns.
- [x] Return the reviewer to Home after approval while keeping the success toast visible.
- [x] Remove the standalone Home hero and place export/ingest actions in the source-table header.
- [x] Remove the synthetic "1 failed" product count when an entire image extraction attempt fails.
- [x] Remove the raw filename from the source-detail metadata line.
- [x] Add a status filter to the uploaded-sources table using the displayed review states.
- [x] Persist source-detail selection and active image reading in the URL, restoring it on refresh and browser navigation.
- [x] Revert the synthetic mapping-confidence fallback and its generated provenance warnings at the user's request.
- [x] Standardize all frontend dropdowns with a shared control style and custom chevron.
- [x] Use the document mapping score for product rows whose field-level assessment is absent or incomplete, without changing JSON extraction.
- [x] Inherit document-level currency into line-item pricing when a line has no explicit override, with a defensive frontend fallback.
- [x] Soften source-row typography and contrast with medium-weight titles, quieter filenames, and restrained file-type labels.

## Context and constraints

- User feedback 1: "This looks too messy and too scary. Almost like actual errors. Also after a user reviews can we change the status and show a toast to the user".
- User feedback 2: "Extraction failed is a state not a warning or an error message. Let it show as a state".
- In `scan_03_glare_partial_andina_p1.jpg`, both OCR and vision direct failed due to glare/quality gate.
- Three red banners were previously showing simultaneously: top `errorMessage` banner (from 409 thrown by watcher calling `openImageExtractionForReview`), header failure banner, and bottom failure banner.
- The review system previously updated backend `document.status` and `quotation.review_status` to `"approved"` or `"rejected"`, but the UI displayed "Ready" instead of "Approved", and lacked any toast notification upon submission.
- When an initial revision removed the red banners and introduced a calmer yellow warning card at the top, user clarified that extraction failure is a document state, not an alert or warning banner.

## Decisions & Implementation

1. **State vs. Warning Presentation (`SourceDetailHeader.vue`)**:
   - Removed the floating alert/warning banner above `← Back to sources`.
   - Converted "← Back to sources" to a semantic navigation link (`<a href="#" role="button" @click.prevent="emit('back')">`).
   - Integrated extraction failure details directly inside the main card in an `Extraction state` section (`bg-surface-alt border border-rule text-xs`).
   - Placed the "Extract again" button for JSON sources inside the primary action button bar alongside "Open original".
   - Added explicit "Approved" / "Rejected" confirmation pills in the action button bar.
   - Conditionally rendered the 4-column metadata strip only when `document.quotation` exists (`v-if="document.quotation"`).
   - Added subtle `Unclear` indicator badges on failed peer reading approach switcher buttons.

2. **Dashboard & Status Consistency (`SourceTable.vue`)**:
   - Updated `statusLabel` and `statusKey` so reviewed sources display `APPROVED` (green badge) or `REJECTED` (red badge) instead of `Ready`.

3. **Coordinator & Toast System (`App.vue`)**:
   - Added reactive `toast` state with smooth slide/fade entrance and auto-dismissal (4 seconds) with manual close button.
   - Dispatched success toast on approval ("Source Approved: Quotation approved and marked ready for commercial export.").
   - Dispatched info toast on rejection ("Source Rejected: Quotation marked as rejected (<reason>).").
   - Dispatched success toast on field correction ("Correction Saved: Field updated successfully.").
   - Guarded `openCandidateForReview` to only promote completed extraction attempts, avoiding the 409 Conflict error.
   - Replaced duplicate failed extraction box with a clean neutral empty state: "No line items extracted".

4. **Testing (`App.spec.ts`)**:
   - Added test verifying failed image attempts do not trigger `openImageExtractionForReview` or display error banners.
   - Added test verifying approval triggers success toast and updates status to "Approved".
   - Added test verifying rejection triggers info toast and updates status to "Rejected".
   - Added coverage for the four status labels/colors and in-platform JSON preview.
   - All 28 frontend unit tests pass.

5. **Source preview and action refinement**:
   - Added `SourcePreviewModal.vue`, which fetches the source within the platform and renders formatted JSON/text/email, images, PDFs, and browser-readable fallbacks.
   - Replaced Home filename downloads and detail-page new-tab links with the shared preview.
   - Replaced the text `Delete` action with a labeled trash icon.
   - `Pre-approved` denotes a successful pending-human-review extraction with zero mapping issues; it does not bypass mandatory human approval.

## Verification

```bash
bin/agent-validate targeted
```
Output:
- Frontend lint: `eslint . --max-warnings=0` passed (0 errors, 0 warnings).
- Frontend tests: `vitest run` passed (26 passed).
- Backend lint: `ruff check backend` passed.
- Backend types: `mypy app` passed (27 source files).
- Backend tests: `pytest backend/tests` passed (98 passed).

Limitation:
- The user explicitly asked to skip browser testing for speed, so this follow-up is verified through component tests, lint, build, and repository validation only.

## Review findings and resolutions

- Systems: source retrieval remains on the existing application API boundary; no persistence or backend contract changed.
- Quality: pending sources are only Pre-approved when a mapping score exists and issue count is zero; missing assessments remain Needs review.
- UX/accessibility: preview actions are buttons, the trash icon retains a descriptive `aria-label`, and the dialog supports Escape, backdrop close, initial close-button focus, and loading/error states.
- Security/performance: source content is fetched only on demand, object URLs are revoked on close, and text formats are rendered as text rather than injected HTML.
- Independent provider review was unavailable; `bin/agent-review` requested persona passes, recorded above.

## Handoff / remaining work

- `bin/agent-validate targeted` passed: frontend lint and 28 component tests, backend Ruff/mypy, and 98 backend tests.
- `bin/agent-validate full` passed lint, component tests, build, backend checks/tests, and stored evaluations. Its Playwright phase could not launch because the local Chromium executable is not installed. Per the user's request, no browser installation or further browser testing was attempted.
- Existing uncommitted changes predated this request and overlap the same UI files, so no commit or worksheet tag was created automatically.
