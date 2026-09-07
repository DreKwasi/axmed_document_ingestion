# Backend Evaluation Assets

> Purpose: versioned inputs and approved expected outputs for pipeline evaluations.
> Run: `backend/bin/run-evals` runs regression checks and persists a recorded SQLite run.
> Default: recorded mode never calls a model; `--live` and `--email` explicitly enable model evaluation; `--ocr` calls only the OCR service.
> Fixtures: `fixtures/documents/` contains source documents; `fixtures/ocr/` contains degraded image inputs.
> Ground truth: only `golden_outputs/` reviewed from source documents is used for fidelity scoring.
> Email privacy: the Novara source is retained as an eval fixture; greetings, signatures, email addresses, phones, and contact-address material are removed before model context is constructed.
> OCR scope: the glare fixture is partial and validates OCR resilience, not full-quotation fidelity.
> Search terms: eval, golden, OCR, fixture, ground truth, SQLite.

## Layout

- `golden_dataset.json` — versioned cases and rubric.
- `golden_outputs/` — reviewed expected canonical outputs.
- `recorded_json_extractions/` — immutable per-document semantic fact responses for offline regression checks.
- `fixtures/documents/` — document inputs used by the current golden cases.
- `fixtures/ocr/` — real degraded image inputs for the OCR layer.

## OCR fixtures

| Fixture | Intended check | Score boundary |
| --- | --- | --- |
| `scan_02_lowres_fax_andina_p1.png` | Low-resolution fax; runs through image intake and PaddleOCR. Its visible content corresponds to the Andina quotation source. | OCR evidence and extraction can be compared after a reviewer approves an image-specific expected output. |
| `scan_03_glare_partial_andina_p1.jpg` | Glare, perspective distortion, and partial table visibility. | OCR should return safe evidence; it must not be scored as a complete quotation. |

Run `backend/bin/run-evals --ocr` to execute the OCR anchors against the configured PaddleOCR service and persist the result in SQLite. It does not invoke an LLM.

Run `backend/bin/run-evals --email` to execute reviewed email cases, including correction precedence, through the configured structured-extraction model.
