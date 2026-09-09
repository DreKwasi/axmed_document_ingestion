# Agent Planning and Execution Summary

> **Agent-generated submission artifact**  
> **Project:** Axmed Supplier Document Intelligence  
> This summary is generated from the current codebase and its implementation worksheets. It describes the planning and execution collaboration; it is not a verbatim transcript.

## The candidate's role

The candidate was the **primary implementation author** of this project. They wrote the application code and used the agent as a planning, research, debugging, and review collaborator—not as an autonomous owner of implementation. They defined the objective—turn supplier quotations in JSON, email, PDF, and image form into reviewable pharmaceutical procurement data—and set the non-negotiable boundaries that guided the agent's contributions:

- Human reviewers, not the model, make approval and rejection decisions.
- Models interpret source material and propose grounding; application code owns routing, validation, commercial calculations, persistence, confidence, and state transitions.
- Evidence must be checkable against the source. Unsupported or ambiguous values stay reviewable rather than being asserted as facts.
- Work is delivered as small, tested vertical slices with a worksheet, system-document updates, application checks, and validation evidence.

The candidate also actively corrected course when agent-assisted approaches drifted or overcomplicated the architecture. The early schema-learning cache, separate Huey worker, persisted batch entity, and open-ended LangChain-agent loop were useful experiments recorded in the worksheets, but they are not part of the current product. The candidate redirected the implementation toward one FastAPI application, one SQLite database, API-owned background work, and per-document semantic extraction.

## How planning evolved

The worksheets show an iterative, evidence-led development process:

1. **Foundation and review controls.** The first JSON slice established FastAPI, Vue, SQLite, safe source storage, and the review desk. The next slice separated quoted supplier values from deterministic derived values and added correction, approval, and rejection actions.
2. **Formats and operations.** Email, native-PDF, OCR/image, progress-event, and multi-file paths were added as discrete seams. Each format preserves a source-specific representation rather than forcing all inputs into one lossy table format.
3. **Semantic reliability.** The initial mapping/reuse and agent-loop approaches exposed failure modes: stale cross-document assumptions, unclear workflow termination, and unsupported evidence. The candidate guided the replacement with application-controlled extraction, grounding, and a finite repair loop.
4. **Review clarity.** Later worksheets refined source evidence, mapping confidence, low-quality image handling, CSV export, review labels, and the Vue inspection experience so uncertainty is visible and actionable.

This trajectory is documented in `docs/worksheets/di-01-schema-learning-json.md` through `di-10-langchain-gemini.md`, `di-17-langchain-semantic-agent.md`, and `orchestrated-structured-extraction.md`. Historical worksheets remain the execution record; the description below reflects the code that remains today.

## Current implementation the candidate delivered

```text
                                      ┌──────────────────────────────────────────────────┐
                                      │ Vue 3 review workspace                            │
                                      │ source table · detail drawer · review controls    │
                                      │ SSE activity timeline · source preview · CSV      │
                                      └───────────────────────────▲──────────────────────┘
                                                                  │ REST + SSE
┌──────────────┐   ┌─────────────────────────────────────────────┴──────────────────────┐
│ Supplier file│──▶│ FastAPI intake                                                     │
│ JSON · EML   │   │ media/size validation · generated storage name · DocumentRecord    │
│ PDF · PNG/JPG│   │ independent source records; bad siblings fail in isolation          │
└──────────────┘   └───────────────────────────┬────────────────────────────────────────┘
                                                │ bounded API-owned background executor
      ┌──────────────────┬──────────────────────┼──────────────────────┬──────────────────┐
      ▼                  ▼                      ▼                      ▼                  ▼
┌───────────┐      ┌──────────┐           ┌────────────┐        ┌─────────────┐    ┌──────────────┐
│ JSON      │      │ EML      │           │ Native PDF │        │ Image       │    │ Processing   │
│ profile   │      │ MIME +   │           │ LiteParse  │        │ PaddleOCR + │    │ events       │
│ paths +   │      │ contact  │           │ reading    │        │ direct      │    │ persisted +  │
│ samples   │      │ redaction│           │ order/layout│       │ vision peers│    │ replayed SSE │
└─────┬─────┘      └────┬─────┘           └─────┬──────┘        └──────┬──────┘    └──────────────┘
      └─────────────────┴───────────────────────┴─────────────────────┘
                                                │
                                                ▼
                     EvidenceWorkspace: addressable JSON paths, email spans, PDF/OCR pages
                                                │
                                                ▼
                         application-controlled extraction, grounding, and investigation
                                                │
                                                ▼
              deterministic commercial rules · provenance · dual confidence · human review
                                                │
                                                ▼
                  SQLite: sources, quotations, fields, evidence, facts, reviews, events
```

- `backend/app/api.py` exposes multi-file upload, document retrieval, source download/deletion, progress events, re-extraction, human review, image-attempt review, and CSV export.
- `backend/app/documents.py` owns intake, document state, storage, persistence, and review commands.
- `backend/app/extraction/` contains JSON, MIME email, native-PDF, OCR/image, semantic-extraction, commercial-rule, confidence, and evidence-workspace code.
- `frontend/src/` contains the Vue review workspace, source previews, product details, review controls, and processing-activity UI.

### Intake and source boundaries

One `POST /api/v1/documents` endpoint accepts JSON, EML, PDF, PNG, and JPEG files. Media validation and format routing are deterministic. Multiple files become independent source records, so one invalid file is recorded as failed without discarding usable siblings. Original uploads are stored under generated names and can be retrieved or deleted with all document-scoped derived state.

### Bounded semantic extraction and source grounding

The candidate implemented the following application-controlled investigation loop, after correcting earlier agent-assisted approaches that allowed too much model-directed control. The model is called only at the three labelled semantic stages; Python selects every transition, validates every claim, and owns termination.

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ 1. Prepare deterministic EvidenceWorkspace                                  │
│    whole JSON/email or addressable PDF/OCR pages + source-specific context  │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 2. PRIMARY EXTRACTION — structured model call                               │
│    returns canonical quotation values + reviewer narrative; no evidence     │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 3. Python validation                                                        │
│    schema/completeness + deterministic commercial rules                      │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 4. FULL GROUNDING — structured model call                                   │
│    receives exact populated fields; returns only field/value/source claims  │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 5. Python grounding validation                                              │
│    canonical field exists? reference resolves? source contains claimed      │
│    value? direct value agrees? JSONPath exists and matches?                  │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   │
                   ┌───────────────┴────────────────┐
                   │ all fields grounded             │ missing/invalid evidence
                   ▼                                 ▼
              persist evidence              ┌────────────────────────────────┐
                                            │ 6. EVIDENCE INVESTIGATION LOOP   │
                                            │ model receives all unresolved    │
                                            │ fields + rejected claims; may    │
                                            │ return evidence claims only      │
                                            └───────────────┬────────────────┘
                                                            ▼
                                            Python revalidates and attaches only
                                            accepted claims
                                                            │
                               ┌────────────────────────────┴───────────────────────────┐
                               │ new valid claims and fewer than three runs → repeat     │
                               │ no progress or three runs → retain unresolved warnings  │
                               └────────────────────────────────────────────────────────┘
                                                            │
                                                            ▼
                         persist candidate, evidence, source facts, and review issues
```

The model cannot select the next workflow stage, rewrite an already extracted candidate during grounding, persist unvalidated evidence, or approve a document.

A grounding claim is accepted only if code can validate its canonical destination, cited source value, and addressable source reference. JSON documents retain exact JSONPath-backed facts; native PDFs retain layout-aware context; email preparation redacts contact details; and OCR-assisted and direct-vision image results remain peer attempts.

### Deterministic review and commercial controls

Commercial rules derive normalized unit prices only from established facts and label formulas as derived values, never supplier statements. Extraction confidence and mapping confidence are calculated independently from source quality, evidence grounding, association, validation, and conflicts.

Usable quotations enter human review. Reviewers can approve, reject with a required reason, or correct fields through auditable commands. The UI provides source preview, normalized products, field provenance, mapping concerns, confidence, and persisted processing events to make that decision in context.

### Confidence calculations the candidate required

The candidate required confidence to be derived from observable evidence rather than a model self-rating. The implementation consequently keeps source recovery separate from source-to-schema certainty.

**Extraction confidence** is a document-level source-recovery score:

```text
round(0.30 × machine_readability + 0.25 × parser_quality + 0.45 × text_legibility)
```

- Readability is 100 for JSON, recovered email text, and native-text PDF; 40 when OCR is required; and 70 for another readable unstructured source.
- Parser quality is 100 for `good`, 70 for `mixed`, 40 for `poor`, 0 for `failed`, and 85 when no parser warning exists.
- Text legibility is 100 without OCR. With OCR, it is the average of mean line confidence and the percentage of OCR lines at or above 0.80 confidence.
- Scores are **High** at 85+, **Medium** at 65–84, and **Low** below 65. A source with no extracted result has no extraction-confidence score.

**Mapping confidence** is computed for every populated canonical field from persisted evidence:

| Evidence or validation state | Field score |
| --- | ---: |
| Direct JSON mapping or human correction | 100 |
| Addressable table row, column, or cell | 92 |
| Grounded source path or location | 82 |
| Evidence exists but no precise location | 70 |
| Contradictory category or commercial validation | 30 |
| No source-linked evidence | 0 |

Passing commercial checks—`quantity × unit price × (1 − discount) = extended price` or `unit price × units per pack = pack price`—adds 5 points to affected fields, capped at 100. The aggregate mapping score is `round(sum(field scores) / populated fields)`.

This distinction is deliberate: a grounded email value can score 82 without a mapping issue because its source text supports it but lacks the explicit field key available in JSON. Mapping issues are reserved for missing evidence, contradictions, ambiguities, or invalid mappings. `pre_approved` requires both scores to be 100 and no mapping issues; every other usable result remains `pending_review` for a human decision.

## How the candidate improved the outcome

The candidate's hands-on authorship and course correction protected the product's trust boundary. When agent-assisted approaches drifted or introduced unnecessary complexity, the candidate intervened and corrected the implementation direction. That guidance made the final system less speculative and more reviewable: deterministic work stayed in code, the model's claims became executable assertions, failures became isolated source states, and historical implementation ideas were removed when they no longer served the current product.

The repository now contains the FastAPI backend, Vue 3 review application, migrations, fixtures, backend and frontend tests, and browser coverage written and integrated by the candidate. The worksheets provide the detailed audit trail; this file is the submission-facing account of how the candidate used, guided, and corrected an agent while building the current implementation.
