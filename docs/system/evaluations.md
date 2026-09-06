# Evaluation System

> Purpose: define how model and pipeline behavior is evaluated, stored, reviewed, and improved.
> Status: implemented baseline — rubric, golden cases, runs, results, and the Vue evaluation lab are SQLite-backed.
> Owner persona: quality engineer with domain-review input for ground truth and scoring thresholds.
> Source guidance: `https://eval.playbook.org.ai/model-behaviour` (Level 1 model evaluation).
> The initial rubric is canonical fidelity, mapping efficiency, and safety/uncertainty; all require explicit pass criteria.
> Search terms: evaluation, rubric, golden dataset, model behavior, scoring, red team, error analysis.
> Never use model-generated output as unreviewed ground truth; domain experts author or materially verify expected behavior.

## Implemented baseline

`evals/golden_dataset.json` defines a versioned rubric and cases. `evaluation_cases`, `evaluation_runs`, and `evaluation_results` persist the definition, execution mode, scores, and error analysis in SQLite. The Vue **Evaluation lab** reads that data and triggers the deterministic recorded evaluation endpoint. This is Level 1 model evaluation: it asks whether the system performs its specified extraction and safety behavior, without claiming product engagement or downstream impact measurement.

The Sanova case checks a full cold-to-warm contract: an unfamiliar schema receives a recorded semantic mapping; a reviewer-confirmed mapping is then reapplied to a same-shape payload with one changed value. It records cold/warm calls, tokens, estimated cost, duration, and business-value parity outside the intended changed value. The recorded fixture is a deterministic stand-in for normal CI, never proof of live-model quality.

## Growth plan

Grow to a 30–50 case minimum viable evaluation set before delivery. Cover native JSON, changed schemas, email correction precedence, native PDF quality, OCR degradation/null correctness, price tiers, combination strengths, PII redaction, malformed structured output, and prompt-injection-like document content. For each case record source, expected output, comparison strategy, rubric threshold, reviewer, and known limitations.

Run deterministic evaluations in CI. Run live provider evaluations separately, label them with provider/model/prompt/version/environment, persist only safe metrics and redacted artifacts, and route failures into error analysis and new golden cases. Add red-team cases whenever a real failure mode is observed. Treat evaluation as continuous: a change to model, prompt, document corpus, configuration, or resolver requires a recorded re-run rather than relying on a previous score.

The deployed OCR service has a separately reproducible warm-performance measurement. See `docs/worksheets/di-06-modal-ocr.md`; it is operational evidence, not a replacement for the SQLite-backed behavioral evaluation corpus.
