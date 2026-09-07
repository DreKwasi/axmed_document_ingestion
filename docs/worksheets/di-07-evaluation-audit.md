# DI-07 — Evaluation evidence audit

> Goal: assess what the SQLite-backed evaluation system can prove against the PRD.
> Scope: deterministic schema reuse, live OCR operational behavior, and field-level corpus accuracy.
> Evidence: `backend/evals/golden_dataset.json`, SQLite evaluation records, Modal benchmark, and automated tests.
> Owner: quality engineer plus a commercial-domain reviewer for ground truth.
> Status: active; approved field-level ground truth exists, and native-PDF table fidelity remains under evaluation.
> Search terms: evaluation, ground truth, fidelity, OCR, schema reuse, benchmark.

## Verified

| Requirement | Evidence | Status |
| --- | --- | --- |
| SQLite-backed evaluation definitions, runs, and results | `evaluation_cases`, `evaluation_runs`, and `evaluation_results`; API and browser E2E coverage | complete |
| Live PDF golden evaluation | Farmaceutica Andina and Mekong source PDFs, source-verified expected JSON, field-level SQLite result records | complete |
| Deterministic schema reuse | Sanova cold/warm recorded case: one cold mapping, zero warm calls/tokens/cost | complete |
| OCR operational performance | Modal warm benchmark: p50 3,494.21 ms, p95 4,551.45 ms for the low-resolution fax | complete |
| OCR evidence fidelity | `backend/bin/run-evals --ocr`: low-resolution fax requires all eight approved source anchors; glare/partial image requires two of five, with a partial-document boundary | complete |
| Email correction precedence and UOM fidelity | `backend/bin/run-evals --email`: 1/1 passed. It retains the legally relevant supplier entity while removing contact PII, applies the EUR 0.134 correction, and preserves the explicit `box` UOM. | complete |
| Safe OCR behavior | authenticated service, contract validation, two degraded-image smoke checks, and API-to-review flow | complete |

## Not yet proven

The PRD asks for field-level exactness, numeric tolerance, null correctness, email-correction precedence, OCR degradation handling, price tiers, and combination-medicine pairing across the supplied corpus. Farmaceutica Andina and Mekong have source-verified expected outputs, but the latest `--live` run still fails both PDF cases because the structured model misreads labelled table columns. The two supplied OCR fixtures have approved evidence-level anchors; the glare image deliberately remains excluded from complete-quotation scoring. The supplied Novara EML has an approved canonical case and a passing live run persisted in SQLite.

Do not generate expected answers from the currently configured model and call them ground truth. A commercial-domain reviewer must approve the canonical expected fields and tolerances for each corpus case. After that, add cases to `backend/evals/golden_dataset.json`, run them through the same SQLite-backed execution path, and persist failure analysis for every mismatch.
