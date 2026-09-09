# Evaluation System

> Purpose: define how model and pipeline behavior is evaluated, stored, reviewed, and improved.
> Status: implemented baseline — rubric, golden cases, runs, results, and the Vue evaluation lab are SQLite-backed.
> Owner persona: quality engineer with domain-review input for ground truth and scoring thresholds.
> Source guidance: `https://eval.playbook.org.ai/model-behaviour` (Level 1 model evaluation).
> The initial rubric is canonical fidelity, mapping efficiency, and safety/uncertainty; all require explicit pass criteria.
> Search terms: evaluation, rubric, golden dataset, model behavior, scoring, red team, error analysis.
> Never use model-generated output as unreviewed ground truth; domain experts author or materially verify expected behavior.

## Implemented baseline

`backend/evals/golden_dataset.json` defines a versioned rubric and cases. `evaluation_cases`, `evaluation_runs`, and `evaluation_results` persist the definition, execution mode, scores, and error analysis in SQLite. The Vue **Evaluation lab** reads that data and triggers recorded evaluation without a provider, or the live PDF pipeline when Gemini is configured. Live summaries derive their case count from the selected dataset cases. This is Level 1 model evaluation: it asks whether the system performs its specified extraction and safety behavior, without claiming product engagement or downstream impact measurement.

The Sanova case checks source-grounded JSON extraction against a recorded response. The response is keyed to the exact source-content hash for repeatable offline evaluation; it is not a reusable schema mapping and does not establish a zero-model path for similarly shaped documents. The evaluation verifies canonical business values, recovered source facts, JSONPath/value grounding, and telemetry. A recorded fixture is a deterministic stand-in for normal CI, never proof of live-model quality.

The Farmaceutica Andina and Mekong PDF cases reference source fixtures and source-verified expected canonical JSON under `backend/evals/`. With Gemini configured, an evaluation run executes the live native-PDF pipeline (parse, redact, structured extraction, deterministic commercial rules) and persists field-level diffs in SQLite. Without credentials, those cases are explicitly marked `not_run`; they never count as passing recorded tests.

The Novara EML case uses the same model-evaluation path for email parsing, deterministic PII minimization, structured extraction, correction precedence, and commercial rules. The email fixture is retained as source evidence, but the model context excludes greeting/signature contact material before evaluation while retaining a legal supplier entity where one is explicitly identified. A source price UOM reconciles model output only when both item and amount match.

## UOM and packaging semantics

`quoted_price.uom` is the source's stated commercial basis, not a normalized inventory unit. A `box`, `pack`, `kit`, `vial`, or supplier-specific term remains exactly that value. Packaging fields independently describe the container and its contents (`primary_pack`, `units_per_pack`, and `unit_label`). Deterministic code may preserve an explicit, item-and-amount-matched source UOM and calculate prices only from established facts; it never invents a fallback UOM. The structured reasoning layer maps unfamiliar price fields and packaging relationships, leaving uncertainty null for review when the source is ambiguous.

## Growth plan

Grow to a 30–50 case minimum viable evaluation set before delivery. Cover native JSON, changed schemas, email correction precedence, native PDF quality, OCR degradation/null correctness, price tiers, combination strengths, PII redaction, malformed structured output, and prompt-injection-like document content. For each case record source, expected output, comparison strategy, rubric threshold, reviewer, and known limitations.

Run deterministic evaluations in CI. Run live provider evaluations separately. Each live PDF result stores provider, model, canonical prompt version, environment, duration, safe field-level failure analysis, and redacted artifacts only. Route failures into error analysis and new golden cases. Add red-team cases whenever a real failure mode is observed. Treat evaluation as continuous: a change to model, prompt, document corpus, configuration, or resolver requires a recorded re-run rather than relying on a previous score.

The deployed OCR service has a separately reproducible warm-performance measurement. See `docs/worksheets/di-06-modal-ocr.md`; it is operational evidence, not a replacement for the SQLite-backed behavioral evaluation corpus.

## Running evaluations

Run `backend/bin/run-evals` from the repository root (or `./bin/run-evals` from `backend/`). It loads `backend/.env`, runs `tests/test_evaluations.py`, applies migrations, and persists the recorded SQLite run. It does not call a model. Pass `--live` only when a configured provider should run the live PDF cases, `--email` for reviewed email cases, or `--ocr` to run the configured OCR service against approved OCR anchors; OCR mode invokes no extraction model.
