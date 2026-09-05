# False-Confidence Test Audits

> Purpose: periodically find tests that pass without protecting the intended production behavior.
> Run on a focused change and in periodic sweeps with `bin/false-confidence-audit`.
> Audit tests by mutating or removing the protected behavior where safely possible.
> Owner persona: quality engineer.
> Related: testing, test catalog, agent review.
> Search terms: mutation, mock, assertion, false confidence, audit.
> Fix weak tests and update the catalog instead of only reporting suspicion.

## Audit checklist

- Would the test fail if the intended branch, validation, or output were wrong?
- Are mocks hiding an integration boundary that should be exercised?
- Does the assertion check a meaningful output/state rather than a call count alone?
- Are setup and selectors deterministic and representative of a real user journey?
- Does an E2E test run against the app and observe a user-visible outcome?
