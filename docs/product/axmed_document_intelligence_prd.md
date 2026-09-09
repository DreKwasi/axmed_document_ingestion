# Axmed Document Intelligence Agent

## Product Requirements Document

**Project:** Supplier Document Intelligence 
**Context:** Axmed AI Engineer Take-Home Assignment 
**Primary stack:** Python / FastAPI + Vue 3 
**Document status:** Working implementation specification
**Canonical specification:** This is the sole versioned PRD for this repository. Historical drafts are source material, not parallel requirements.

---

# 1. Product overview

Axmed receives supplier quotations and commercial product information in formats that vary significantly between suppliers.

The same underlying information may arrive as:

- structured supplier JSON exports
- digitally generated quotation PDFs
- email threads
- scanned quotation sheets
- photographs of documents
- low-resolution or partially obscured images

The underlying challenge isn't simply extracting text.

The system needs to determine what a supplier is actually offering, convert that offer into a consistent commercial data model, identify when information is ambiguous or unreliable, and present the result to a human before anything is accepted into a downstream system.

The proposed system is therefore a **document intelligence and human-review pipeline** rather than a generic OCR service.

---

# 2. Product objective

Build a system that can ingest heterogeneous supplier documents and produce reviewable structured quotation records.

For each uploaded document, the system should:

1. Determine what type of document it received.
2. Extract usable document content using the cheapest reliable path.
3. Escalate poor-quality image content to OCR.
4. Remove unnecessary PII before sending content to external language models.
5. Convert supplier-specific structures into a canonical quotation model.
6. Normalize commercial and pharmaceutical information where possible.
7. Preserve the distinction between supplier-provided and system-derived values.
8. Validate extracted values against deterministic business rules.
9. Attach uncertainty and provenance to extracted information.
10. Allow a human reviewer to approve, reject, or correct the result.

The pipeline should keep deterministic parsing, validation, calculation, persistence, and review authority outside semantic interpretation. Repeated supplier schemas are not automatically trusted or reused; each document must retain source-grounded evidence for its canonical claims.

---

# 3. Product principles

## 3.1 Deterministic where possible

An LLM shouldn't be the first tool used for every problem.

If a JSON field already says:

```json
{
 "price_per_pack": 3.15,
 "units_per_pack": 90
}
```

we don't need an LLM to calculate:

```text
3.15 / 90 = 0.035 per tablet
```

The system should use ordinary software whenever the relationship is known.

LLMs should primarily handle semantic ambiguity.

## 3.2 Preserve the supplier's original meaning

Normalization must not destroy source information.

If the supplier quoted:

```text
EUR 3.15 / pack
```

the database should retain that exact commercial basis even if the system derives:

```text
EUR 0.035 / tablet
```

The latter is a calculated value.

They shouldn't become indistinguishable.

## 3.3 Uncertainty is a valid output

The pipeline should prefer:

```text
price = unknown
confidence = low
requires_review = true
```

over confidently inventing a value.

This is particularly important for blurred scans, cropped documents, conflicting correspondence, and implied commercial terms.

## 3.4 Human approval remains the trust boundary

Extraction completion does not mean quotation acceptance.

The pipeline prepares information for a reviewer.

Only reviewed or approved records should be considered ready for downstream use.

---

# 4. Evidence from the supplied test corpus

The supplied documents demonstrate why the initial schema is insufficient.

The Farmaceutica Andina quotation contains line quantities, dosage strength and form, pack descriptions, unit price, percentage discount and extended line price. It also specifies FOB Cartagena terms, quotation validity, shipping information, shelf-life conditions and minimum-order restrictions.

The Mekong quotation adds pack price, MOQ in packs, lead times, product regulatory information, storage requirements, CIF terms and a rule that orders below MOQ may incur a 12% surcharge.

The Novara email demonstrates semantic revision. Azimax is first quoted at EUR 0.128/tablet and later corrected in the P.S. to EUR 0.134/tablet. A simple first-match extractor would return the wrong commercial value.

Sanova's JSON explicitly states that unit prices aren't provided. Instead, pack prices and pack composition are supplied, meaning unit prices must be derived.

Ubuntu introduces volume-dependent pricing tiers and explicitly states that VAT is excluded.

Zenith includes dosage form, manufacturer, country of origin, regulatory qualification, cold-chain requirements, and shipment HS codes alongside commercial data.

The canonical model therefore needs to represent both the medicine and the commercial context around its price.

---

# 5. High-level architecture

```text
                         INPUT
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
        STRUCTURED                 UNSTRUCTURED
           JSON                PDF / EMAIL / IMAGE
              │                         │
              ▼                         ▼
     Schema recognition         Format-specific parsing
              │                         │
              │                  ┌──────┼─────────┐
              │                  │      │         │
              │               PDF     Email     Image
              │                  │      │         │
              │             LiteParse  MIME    PaddleOCR
              │                  │      │         │
              │                  └──────┴─────────┘
              │                         │
              │                         ▼
              │              Parsed document representation
              │                         │
              │                         ▼
              │                   LLM extraction
              │                         │
              └──────────────┬──────────┘
                             ▼
                    CanonicalQuotation
                             │
                             ▼
                 Deterministic validation
                     + derivation
                             │
                             ▼
                 Confidence + provenance
                             │
                             ▼
                       Human review
```

The core split is based on whether the source already exposes reliable machine-readable structure.

Structured sources are mapped into the canonical quotation schema with deterministic schema recognition wherever possible.

Unstructured sources are first converted into the best available document representation, then interpreted semantically by the LLM.

Both paths converge at the same canonical quotation model and deterministic commercial-rules layer.

---

# 6. Technology decisions

## Backend

**FastAPI**

Chosen because the implementation is Python-first, lightweight and naturally compatible with the wider document-processing ecosystem.

Axmed primarily operates within Python, so the architecture remains close to their existing technical environment even though their application framework is Django.

## Frontend

**Vue 3 + Vite + TypeScript**

Using Composition API with `<script setup>`.

The UI should remain intentionally small.

Its purpose is to demonstrate the operational workflow rather than become a large frontend application.

Primary surfaces:

- upload
- processing status
- extracted quotation table
- flagged uncertainty
- source evidence
- review controls

## Local persistence

**SQLite**

No externally deployed database is required.

Application state lives locally in `data/app.db`.

## Background processing

**API-owned Python background tasks**

For the current single-process implementation, FastAPI schedules document-specific Python background tasks after the upload response is sent. No separate queue database or worker process is required.

The API writes safe terminal lifecycle logs for every task: scheduled, started, completed with duration, or failed with only an error type. Logs include a short document/job identifier and never source text or credentials; persisted processing events remain the browser-facing progress record.

Background tasks handle operations that may be:

- slow
- remote
- model-dependent
- retryable
- computationally expensive

A document, rather than an entire folder, should generally be the useful unit of asynchronous work.

That means one bad scan doesn't prevent unrelated clean documents from completing.

---

# 7. Sync vs async processing

The system should not push all document work into background tasks by default.

Fast, deterministic work stays in the normal FastAPI request flow. Slow or model-dependent work is scheduled by the API after the source has been persisted.

## Synchronous fast path

Typical synchronous work includes:

```text
Upload
 ↓
File validation
 ↓
Document type detection
 ↓
JSON parsing / MIME parsing / LiteParse
 ↓
Persist parsed representation
 ↓
For JSON: profile, extract, validate, normalize, and persist source facts
 ↓
Respond
```

Examples:

- JSON parsing
- MIME parsing for email
- LiteParse for digitally generated PDFs
- basic image validation
- per-document JSON structural profiling

## Async path

The API-owned background task handles work where runtime is less predictable:

```text
Parsed source
      ↓
OCR escalation if required
      ↓
PII detection / redaction
      ↓
LLM semantic extraction
      ↓
Normalization
      ↓
Validation + derivation
      ↓
Confidence + provenance
      ↓
Persist results
```

The useful unit of background work is generally one document, not an entire uploaded folder.

---

# 8. Async path

API-owned background tasks handle operations with unpredictable runtime or external dependencies.

```text
Parsed document
 ↓
OCR if necessary
 ↓
PII scan/redaction
 ↓
LLM semantic extraction
 ↓
Reconciliation
 ↓
Normalization
 ↓
Validation
 ↓
Confidence/provenance
 ↓
Persist results
```

---

# 9. Frontend processing updates

Use **Server-Sent Events**.

The API background task does not communicate directly with browser connections.

Instead:

```text
API background task
 ↓
writes processing state/event
 ↓
SQLite
 ↓
FastAPI observes new events
 ↓
SSE
 ↓
Vue
```

SQLite therefore becomes the communication boundary.

This keeps processing independent from frontend connection state.

If the browser disconnects, document processing continues normally.

---

# 10. PDF processing

## Primary parser: LiteParse / LlamaIndex document parsing

For digitally generated PDFs, LiteParse is the primary document-recovery layer.

Its job is not to understand the commercial meaning of the quotation. Its job is to recover as much of the document's structure and content as possible, including:

- page text
- table-like structure
- rows and cells where available
- reading order
- page boundaries
- layout information
- OCR-needed signals where available

A successful parser output does not need to match the canonical quotation schema.

For example, a supplier presentation may remain as:

```text
500 mg tablet
PVC/Alu blister, 20 tablets per pack
```

The LLM can then separate this into strength, dosage form, packaging, and units-per-pack during semantic extraction.

The parser should preserve relationships and source context rather than attempting to understand procurement semantics.

### Parser output as source representation

The original LiteParse/LlamaIndex representation should be retained.

A Markdown or cleaned text representation may also be generated for LLM prompting and debugging, but Markdown is not the source of truth.

```text
PDF
 ↓
LiteParse
 ↓
raw structured representation
      +
optional Markdown/text view
 ↓
LLM semantic extraction
 ↓
CanonicalQuotation
```

This avoids throwing away page boundaries, cell relationships, layout metadata, or source locations that may later be useful for provenance and review.

### No generic table-reconstruction rules

The application should not attempt to hand-build a universal table parser for arbitrary supplier PDFs.

Supplier documents may contain merged cells, multi-line headers, mixed narrative and tabular content, nested product descriptions, footnotes, irregular row layouts, or visually positioned text rather than true PDF tables.

The document parser should recover the best representation it can. The LLM then interprets that representation into the canonical schema.

Deterministic logic returns after semantic extraction to validate commercial relationships.

For native PDFs, the model must not stop at the visual price schedule. The pipeline supplies LiteParse's
deterministic layout representation and complete reading-order context to one semantic investigation. The agent must inspect
facts that tables routinely omit and apply explicitly scoped notes—single item, item list/range, exception, or all other items—to the relevant canonical line items.

Examples include shelf life, minimum remaining shelf life, storage and cold-chain conditions, MOQ, registration
references/status, and registered markets. A stated percentage is persisted in percentage points (`80`, not `0.80`).
The agent preserves source-supported table values while incorporating source-supported narrative facts; deterministic validation handles commercial conflicts after extraction.

---

# 11. OCR architecture

**PaddleOCR deployed on Modal**

OCR is a fallback for image-based or degraded content.

```text
PDF
 ↓
LiteParse
 ↓
usable text / table representation?
 ├── yes → LLM extraction
 │
 └── no / scanned / garbled
          ↓
       PaddleOCR
          ↓
       OCR page text + original source
          ↓
       LLM semantic extraction
```

Images generally enter through the PaddleOCR path directly.

OCR should preserve confidence and layout metadata in its stored provider result for audit and future tooling. That
metadata does not drive canonical mapping in the current pipeline and is not supplied to Gemini as a row model.
For images, the system runs two independent Gemini attempts: an OCR-assisted attempt receives readable OCR page text,
and a direct-vision attempt receives the original image. They are peer results, never merged or automatically selected.
A reviewer compares them and explicitly opens one result for quotation review. Neither attempt may assume OCR line order
defines table rows.

The original image remains the ground truth source for review.

---

# 12. Unstructured document extraction

PDFs, images, and emails are treated differently from JSON because their source structure is not guaranteed to align with the canonical schema.

The general flow is:

```text
Unstructured source
      ↓
Best available parser
      ↓
Parsed document representation
      ↓
LLM semantic extraction
      ↓
CanonicalQuotation
      ↓
Deterministic commercial rules
```

## PDF

```text
PDF
 ↓
LiteParse
 ↓
parsed text / tables / layout
 ↓
LLM maps meaning into canonical schema
```

If LiteParse cannot recover useful content, the affected page or document is escalated to PaddleOCR.

## Email

Email first goes through deterministic MIME parsing.

```text
EML
 ↓
MIME parser
 ↓
subject / sender / date / ordered body
 ↓
HTML table structure if present
 ↓
LLM semantic extraction
```

If an HTML table exists, its DOM structure should be preserved.

If the message is plain text, the ordered body is passed to the LLM as natural-language evidence.

The LLM is responsible for semantic cases such as corrections, superseded prices, and commercial terms expressed in prose.

## Image

```text
Image
 ↓
PaddleOCR
 ↓
readable page text
 ↓
Gemini receives original image + OCR transcription
 ↓
semantic extraction
```

There is no deterministic OCR table reconstruction or row mapping. OCR confidence and geometry remain stored for
audit/debugging but do not control Gemini's interpretation.

---

# 13. PII handling

OCR-derived text is redacted before it is sent to the LLM. The OCR semantic path also transmits the original source
media so Gemini can inspect visual content that OCR may have misordered or omitted. This requires an approved model
provider/data-processing boundary because text redaction cannot sanitize pixels in the attached source.

Use:

**Microsoft Presidio**

with a lightweight spaCy English pipeline.

```text
Parsed / OCR'd content
 ↓
Presidio
 ↓
Detect PII
 ↓
Redact unnecessary information
 ↓
LLM
```

Potential redactions include:

- personal email addresses
- phone numbers
- personal names where irrelevant
- banking information
- account identifiers
- unrelated addresses
- other detected personal identifiers

Supplier/company identity should not automatically be removed because it can be material to quotation provenance.

The important principle is **data minimization**.

Only information necessary for extraction should be sent to the model.

---

# 14. Logging and sensitive information

Raw document contents shouldn't be placed into normal application logs.

Avoid:

```python
logger.info(extraction_result)
```

Prefer operational metadata:

```text
document_id
processing_stage
parser_used
ocr_used
fields_extracted
fields_flagged
processing_duration
model_used
token_usage
status
```

Banking details in supplier documents are a good example of information the quotation extraction flow usually doesn't need to expose to the LLM.

---

# 15. Canonical quotation model

The schema is divided into:

1. quotation-level metadata
2. supplier information
3. commercial terms
4. line items
5. product identity
6. packaging
7. quantity
8. pricing
9. supply information
10. regulatory information
11. provenance

---

# 16. Quotation-level schema

Conceptually:

```json
{
 "quotation_reference": null,
 "rfq_reference": null,
 "document_type": null,
 "issue_date": null,
 "valid_until": null,
 "supplier": {},
 "commercial_terms": {},
 "line_items": [],
 "source": {}
}
```

Supported document classes may include:

```text
quotation
proforma
offer
price_list
email_offer
```

The distinction matters because a price catalogue doesn't necessarily represent a specific quantity commitment.

---

# 17. Supplier schema

```json
{
 "name": null,
 "supplier_code": null,
 "country": null,
 "manufacturer": null,
 "manufacturing_site": null
}
```

A product's manufacturer may differ from the quoting supplier, so these concepts shouldn't be permanently collapsed.

---

# 18. Commercial terms

```json
{
 "currency": null,
 "incoterm": null,
 "incoterm_named_place": null,
 "incoterm_country": null,
 "payment_terms": null,
 "freight_included": null,
 "insurance_included": null,
 "tax_included": null,
 "price_basis": null,
 "hs_codes": []
}
```

The Incoterm and named location need to be separate.

For example:

```text
FOB Cartagena
CIF Dar es Salaam
FCA Milan Malpensa
CIP Lagos
```

Two apparently identical medicine prices aren't necessarily commercially comparable when their Incoterms differ.

---

# 19. Product identity

```json
{
 "trade_name": null,
 "inn": [],
 "strength": [],
 "dosage_form": null,
 "manufacturer": null,
 "country_of_origin": null
}
```

`dosage_form` preserves the complete source phrase, such as `solution for injection` or
`powder for oral suspension`. Route is not a separate field, and packaging presentation must not be split out of
or appended to dosage form unless the source states it independently.

---

# 20. Structured strength

Strength should not be limited to a single string.

Combination medicines require ingredient-to-strength association.

Example:

```json
{
 "strength": [
 {
 "ingredient": "Amoxicillin",
 "value": 500,
 "unit": "mg",
 "per_value": null,
 "per_unit": null
 },
 {
 "ingredient": "Clavulanic acid",
 "value": 125,
 "unit": "mg",
 "per_value": null,
 "per_unit": null
 }
 ]
}
```

Concentration:

```json
{
 "ingredient": "Oxytocin",
 "value": 10,
 "unit": "IU",
 "per_value": 1,
 "per_unit": "mL"
}
```

---

# 21. Packaging

```json
{
 "description": null,
 "primary_pack": null,
 "units_per_pack": null,
 "unit_label": null,
 "packs_per_shipper": null
}
```

Always preserve the original pack description.

For example:

```text
Alu-Alu blister, 2 x 7 tablets per carton
```

may yield:

```json
{
 "description": "Alu-Alu blister, 2 x 7 tablets per carton",
 "primary_pack": "Alu-Alu blister",
 "units_per_pack": 14,
 "unit_label": "tablet"
}
```

---

# 22. Quantity

Quantity is explicitly part of the canonical schema.

But it must distinguish different quantity concepts.

```json
{
 "quoted_quantity": null,
 "quoted_quantity_uom": null,
 "quantity_basis": null,
 "minimum_order_quantity": null,
 "minimum_order_quantity_uom": null
}
```

These fields mean different things.

### Quoted quantity

What the supplier has priced.

### Minimum order quantity

Commercial minimum required to access the offer.

### Quantity basis

Useful where the price is dependent on:

```text
annual volume
quarterly volume
tier
indicative RFQ quantity
```

---

# 23. Pricing

Pricing is deliberately split between original and derived values.

```json
{
 "currency": null,
 "quoted_price": {
 "amount": null,
 "uom": null
 },
 "pack_price": null,
 "discount": null,
 "extended_price": null,
 "price_tiers": [],
 "adjustments": [],
 "normalized_price": {}
}
```

---

# 24. Quoted price

This records what the supplier actually stated.

Example:

```json
{
 "amount": 3.15,
 "uom": "pack"
}
```

The value should not be replaced merely because another unit is easier to compare.

---

# 25. Price normalization

Derived pricing lives separately:

```json
{
 "normalized_price": {
 "amount": 0.035,
 "uom": "tablet",
 "calculation": "3.15 / 90",
 "derived": true
 }
}
```

For a pack price of EUR 3.15 and 90 tablets per pack:

```text
EUR 3.15 / 90 tablets
=
EUR 0.035 / tablet
```

This is a system-derived value.

Normalized price is available in product detail for comparison and audit, but it is not repeated in the product
overview table. Its displayed precision must never exceed the quoted price's decimal precision; the stored
`Decimal` value remains exact.

---

# 26. Price tiers

Price tiers require their own data structure.

```json
{
 "price_tiers": [
 {
 "min_quantity": 100,
 "max_quantity": 999,
 "quantity_uom": "pack",
 "price": 41.50,
 "price_uom": "pack"
 },
 {
 "min_quantity": 1000,
 "max_quantity": 4999,
 "quantity_uom": "pack",
 "price": 37.90,
 "price_uom": "pack"
 }
 ]
}
```

Flattening quantity-dependent prices to a single unit price would lose commercial meaning.

---

# 27. Discounts and adjustments

Don't reduce commercial adjustments to one discount column.

Use:

```json
{
 "adjustments": [
 {
 "type": "discount",
 "value": 5,
 "value_type": "percentage",
 "condition": null
 }
 ]
}
```

Potential types:

```text
discount
surcharge
tax
freight
insurance
regulatory_fee
other
```

---

# 28. Supply information

```json
{
 "lead_time_days": null,
 "lead_time_min_days": null,
 "lead_time_max_days": null,
 "shelf_life_months": null,
 "minimum_remaining_shelf_life_percent": null,
 "storage_conditions": null,
 "cold_chain_required": null
}
```

This becomes particularly relevant for temperature-sensitive products such as insulin and oxytocin.

---

# 29. Regulatory information

```json
{
 "who_prequalified": null,
 "who_pq_reference": null,
 "registered_markets": [],
 "registration_reference": null,
 "regulatory_status": null
}
```

This isn't part of the minimum take-home schema, but the supplied documents clearly contain this information.

The architecture should allow extraction even if the first review table exposes only a subset.

---

# 30. Source and provenance

Each resulting line must be traceable back to its source.

At minimum:

```json
{
 "document_name": null,
 "document_format": null
}
```

Internally, provenance should be richer, but a mapping path is lineage—not source evidence—and must not be stored as proof that a field is correct. A field-evidence record is reserved for a source excerpt/location returned by semantic extraction or an auditable human review action. Deterministic validation is stored as a validation result, not presented as source proof.

For a field:

```json
{
 "canonical_field": "pricing.quoted_price.amount",
 "value": 0.134,
 "source_document": "RE_RFQ-2026-0244_Novara_quotation.eml",
 "source_location": "P.S. correction",
 "extraction_method": "llm_extraction"
}
```

---

# 31. Extracted vs derived values

This distinction should exist throughout the system.

Possible origins:

```text
source
llm_extraction
derived
human_corrected
```

Example:

```text
EUR 3.15 / pack
→ source

90 tablets / pack
→ source

EUR 0.035 / tablet
→ derived
```

Human reviewers should be able to see this difference.

---

# 32. JSON semantic extraction without schema reuse

Each JSON upload is interpreted independently as a source document. The system does not store schema fingerprints, mappings, correction-learning records, or aliases for later reuse.

```text
Incoming JSON
 ↓
Profile its structure in memory
 ↓
Recover quotation-relevant source facts
 ↓
Validate each fact's JSONPath and value against the source
 ↓
Assign extraction confidence from source recovery quality
 ↓
Normalize only facts with a certain canonical interpretation
 ↓
Persist all facts, including unmapped facts
 ↓
Human review of the quotation result
```

The profile inventories paths, types, arrays, repeated object shapes, and small contextual samples for this upload only. It is neither persisted as a fingerprint nor reused for another document.

Every quotation-relevant source fact stores its raw value, JSONPath, method, confidence, rationale, normalization status, and optional canonical field. The original JSON remains authoritative.

```text
$.order_info.minimum = "5,000 boxes"
 ↓
source fact recovered and JSONPath/value validated
 ↓
High extraction confidence
 ↓
canonical normalization uncertain
 ↓
persist as an unmapped extracted source fact
```

That is successful source-fact extraction. Canonical-mapping uncertainty never lowers extraction confidence or
creates a review issue. The product-review workflow still requires at least one normalized product line: when
zero products are recovered, the source is marked `failed` with a safe explanation rather than being presented as
pending human review. Any validated source facts remain stored as `not_reviewable`. Invalid claims get one
corrective extraction attempt, while valid facts from the first attempt remain stored.

Canonical quotation fields remain blank when normalization is not certain. `field_evidence` is used only for normalized canonical fields; generic extracted facts are stored separately and are not shown in the current product detail. Human decisions apply to the quotation result, not to a source-schema interpretation.

## 32.1 Bounded semantic investigation

Semantic extraction uses a bounded LangChain `create_agent` investigation loop running in the document background task. Its objective is to produce the most complete source-grounded canonical candidate possible, preserve unmapped facts, and identify unresolved ambiguity. It does not choose the upload route, approve quotations, or override deterministic rules.

```text
Prepared source representation
 ↓
Build stable evidence chunks and a compact source atlas
 ↓
Propose canonical assignments with source evidence
 ↓
Search and inspect related evidence only when more context is needed
 ↓
Run deterministic path, value, reference, completeness, and commercial checks
 ↓
Validation failures or provenance gaps?
 ├── no  → finalize review-ready candidate
 └── yes → return all issues, inspect the conflicting context, and revise while feedback changes and budgets remain
              ↓
          still unresolved → emit a targeted review issue
```

The active loop exposes three capabilities: `search_evidence` for deterministic lexical/structural discovery, `inspect_evidence` for combining related source fragments, and `validate_candidate` for a complete structured issue set. Small sources are passed whole; larger sources use deterministic chunks with stable provenance references and a bounded evidence atlas. The active implementation does not call an embedding provider. An embedding ranker may later improve discovery over the same chunks, but must never replace the source references or deterministic validation.

The active loop is constrained by model-call, per-tool, evidence-volume, and wall-clock limits plus the provider request timeout. Intermediate hypotheses are execution state, not quotation state. Only the final source-grounded candidate is normalized and persisted. A material conflict that remains when feedback stalls or a bound is reached must stay unresolved for human review. LangGraph is a future option if explicit persisted, resumable, operator-tweakable state is required.

The application selects format-specific capabilities deterministically from the validated media type. JSON exposes paths, sibling context, and exact-value checks; PDF exposes native reading order, tables, pages, and regions; email exposes sanitized chronology; images expose accepted OCR lines and masked visual regions. The extraction component decides only which additional evidence to inspect when semantic interpretation remains uncertain.

The target-field knowledge supplied to the extraction component must be richer than a flat alias list. For each canonical field it should provide its meaning, type, required context, related fields, common confusions, permitted derivations, evidence requirements, contradictions, and review triggers. This knowledge is guidance for per-document interpretation, never an exhaustive source-key dictionary or a reusable supplier mapping.

Confidence remains application policy rather than model self-assessment. The extraction component reports observable evidence and conflicts. Deterministic policy calculates extraction confidence from source recovery and mapping confidence from field association, provenance, reconciliation, and contradictions.

---

# 33. Source-fact normalization

JSON key styles vary:

```text
pricePerPack
price_per_pack
PRICE_PER_PACK
Price Per Pack
```

The profile retains the original JSONPaths. Extraction may use normalized key context to understand a single document, but it must not turn key spelling into a stored mapping or infer a canonical field without source support.

---

# 34. Canonical normalization boundary

Normalization is a separate outcome from extraction. The system may populate a canonical field only where the extracted fact has a certain, source-supported meaning. It does not use a global alias registry, fuzzy field matching, or schema memory to force a mapping.

When a fact has an uncertain canonical interpretation, retain its source value and JSONPath as `unmapped`. This is not an exception, a review issue, or a confidence penalty.

---

# 35. Source validation and partial success

For direct JSON facts, resolve the supplied JSONPath and compare the recovered value with the claimed value. For semantic facts, confirm that their source path exists and that their rationale remains consistent with its scoped source context. Invalid claims trigger a single retry that identifies the rejected paths.

The system retains all valid facts from either pass. A partially valid extraction remains successful and may produce a sparse canonical quotation. Only a result with no meaningful, source-grounded quotation facts is failed.

---

# 36. Extracted-source-fact persistence

`extracted_source_facts` is the normalized store for every quotation-relevant fact: document and optional quotation identifiers, label, JSON value, source JSONPath, extraction method, numeric confidence and rationale, normalization status, optional canonical field, and inherited human-review status.

The source-fact record preserves material that does not fit the canonical quotation today. It does not convert uncertain normalization into a failed extraction. Re-extracting an unreviewed JSON source clears its prior machine-generated quotation projection and source facts, then processes the retained original file again. Completed human-review audit records are preserved.

---

# 37. Deterministic derived calculations

Several calculations should never require an LLM.

## Unit price

```text
price per pack / units per pack
```

## Pack price

```text
unit price × units per pack
```

## Extended value

Where applicable:

```text
quantity × quoted price
```

with adjustments such as discount.

These formulas can both derive missing values and validate extracted ones.

---

# 42. Deterministic validation

Examples:

### Currency

Must resemble a valid ISO currency code or recognized currency label.

### Price

Must be positive where applicable.

### Quantity

Must be non-negative and carry a meaningful unit.

### Pack

If:

```text
pack price
units per pack
unit price
```

are all available, verify:

```text
pack_price ≈ unit_price × units_per_pack
```

### Extended price

Verify against quantity and discounts.

### Quotation validity

Validate dates:

```text
issue_date <= valid_until
```

### Percentage adjustment

Reasonable percentage range.

### Price tiers

Ranges shouldn't overlap unexpectedly.

These rules give us confidence signals that don't depend on the model's self-assessment.

---

# 43. LLM responsibilities

Use LangChain as the model abstraction and structured-output layer.

The model should focus on semantic problems such as:

- strange supplier field names
- interpreting free-form emails
- separating medicine name, strength and dosage form
- resolving corrections
- interpreting ambiguous commercial notes
- mapping unfamiliar source fields
- recovering structure from OCR text
- determining whether one statement supersedes another

The LLM should return structured Pydantic-compatible output.

---

# 44. Email extraction

Email requires chronology and discourse interpretation.

The Novara sample demonstrates the issue:

```text
Azimax = EUR 0.128 / tablet
```

followed later by:

```text
Correction...
Azimax = EUR 0.134 / tablet
```

The final value should be:

```text
EUR 0.134
```

while retaining the earlier value as superseded evidence.

Conceptually:

```json
{
 "value": 0.134,
 "supersedes": 0.128,
 "reason": "supplier correction later in message"
}
```

---

# 45. Confidence and extraction correctness

The system exposes two independent confidence measures: **extraction confidence** and **mapping confidence**. Neither is a completeness score or an approval rule; every recovered quotation still requires human review.

## 45.1 Extraction confidence: did we recover the source faithfully?

Extraction confidence is a visible 0–100 score with a `High`, `Medium`, or `Low` band. It is calculated only from source-recovery quality:

| Factor | Weight | Examples |
|---|---:|---|
| Machine readability | 30% | native PDF text and clean email score above OCR-dependent media |
| Parser quality | 25% | clean parse, mixed fallback, poor parse, or failed parse |
| Text legibility | 45% | average OCR confidence plus the share of clearly legible text lines; neutral when OCR is not needed |

The API returns each factor, weight, score, and plain-language reason. Glare, blur, cropping, damaged scans, OCR use, weak OCR lines, and parser warnings reduce extraction confidence. Product count, model self-assessment, OCR/vision agreement, and canonical schema ambiguity never affect it. Each uploaded image exposes its OCR-assisted and direct-vision reading as a separate source result; both share the same source-condition score because they read the same image.

Image-reading confidence remains visible even when an image attempt yields zero products, because it explains whether the source material was usable. When that source-recovery score is below 50%, the image is `Material unusable`: it is terminal, cannot be opened for quotation review, and retains its original material and peer-reading evidence for inspection. At 50% or above, an image with zero recovered products is `Extraction failed`; neither state is a review candidate.

OCR quality has a second role as a hard safety gate before semantic extraction. The default line-confidence floor is 0.80 and at least 60% of detected lines must clear it. If the source fails that gate, no OCR-assisted or vision model extraction runs and the reviewer is told that nothing trustworthy could be extracted. If it passes, only accepted OCR text and accepted image regions may be supplied to the two semantic extraction paths. Thresholds are configurable and must be evaluated against degraded fixtures.

## 45.2 Mapping confidence: did the recovered value land in the correct schema field?

Mapping confidence is calculated per canonical leaf and summarized for each product and source. It combines direct JSON-path grounding, row/cell or source-location association, provenance quality, deterministic reconciliation, and explicit conflicts. A clear `MOQ: 5,000 boxes` can therefore have high extraction confidence while its mapping to `quoted_quantity` has low mapping confidence.

The API returns a deduplicated `mapping_issues` list containing field-level mapping concerns. Every mapped field below 100% produces one issue identifying its canonical field, product-detail section, code, severity, and message; therefore a sub-100 mapping score never displays alongside `No issues found`. A low OCR score does not create mapping issues by itself.

## 45.3 Missing and derived values

An absent source value is not a confidence penalty. A derived value has no extraction or mapping confidence; it retains only its origin, formula, and deterministic validation status.

## 45.4 Review presentation

The source table has `Extraction confidence` and `Mapping confidence` columns. `Review issues` and the opaque `lowest field band` presentation are retired. The mapping column can state, for example, `74% · 2 issues found`.

Product breakdown rows show mapping confidence and their mapping issue count. In product detail, issues appear under the affected Product Identity, Pricing & Commercial Terms, Quantity & Packaging, Supply & Logistics, or Regulatory & Compliance section. Extraction confidence factors remain visible as a separate source-recovery explanation.

If a product has no attributable mapping score and zero mapping issues, the product and source tables show `No issues`; they do not use a dash or invent a percentage.

---

# 46. Review status and human-in-the-loop decisions

Every usable extraction containing at least one product requires human review before it can be approved. Confidence directs attention to
uncertain fields; it never permits approval to be skipped. Image material below 50% source recovery is terminal `Material unusable`, rather than a human-review candidate. There is no auto-approval state.

```text
processing → pending_review → approved | rejected
```

`pending_review`, `approved`, and `rejected` are the persisted source lifecycle statuses. A correction is an
audited action, not a separate terminal status: it preserves each before/after value, sets `has_corrections = true`,
and keeps the source `pending_review` until a reviewer explicitly approves or rejects it.

`approved` means a person inspected and accepted the extracted source. An approval note is optional. `rejected`
requires a structured reason and permits an optional note.

Allowed rejection reasons are:

```text
unreadable_source
incorrect_extraction
unsupported_document
duplicate
not_a_quotation
other
```

---

# 47. Review experience

The review workspace includes every successfully extracted source. It makes full review fast: reviewers can see
what was extracted, which fields deserve attention, each field's source/confidence, and whether a value is
supplier-provided or derived. Low-confidence fields and review issues are visually prominent, but no source is
silently approved.

Example:

| Product | Quantity | Price | Basis | Mapping confidence | Mapping issues |
|---|---:|---:|---|---|---|
| Azimax 250 | — | €0.134 | tablet | 96% | — |
| Sanotri-TLD | — | €0.035 | tablet | 90% | price basis confirmed by reconciliation |
| Scan item | 50,000 | ? | pack | 42% | confirm price field assignment |

Approval is one click. A reviewer may correct values, then explicitly approve the corrected source; corrections
preserve before/after values. Rejection requires a structured reason, not mandatory free text.

---

# 48. Evidence view

For structured text sources, display the relevant source snippet.

For PDFs/images, eventually highlight or identify:

```text
page
table
row
bounding box
OCR segment
```

A reviewer seeing:

```text
price = 0.412
```

should be able to inspect the source location that caused the extraction.

---

# 49. Processing events

Maintain a lightweight processing-event history.

Conceptually:

```text
document_received
document_parsed
ocr_required
ocr_started
ocr_completed
pii_redacted
json_profiling_started
json_semantic_extraction_started
json_source_validation_retrying
normalization_started
validation_completed
review_required
processing_completed
processing_failed
```

These events support both SSE updates and operational debugging.

---

# 50. Failure handling

Failures should be explicit.

### Unsupported file

Reject during intake.

### Corrupted PDF

Fail during synchronous parsing where possible.

### OCR service unavailable

The API records the failure and exposes it through the document status and SSE timeline. A user can retry from the source workflow; automatic retry is intentionally deferred until a durable production queue is introduced.

If the service remains unavailable:

```text
failed
reason = OCR unavailable
```

### LLM returns invalid structure

Retry structured extraction where appropriate.

Then fail or request review rather than accepting malformed data.

### No products extracted

Fail the source with `No products could be extracted from this source.` Preserve any validated source facts for
audit, but do not create an empty quotation for human review.

### Unreadable field

Store null and flag.

---

# 51. Multi-document upload

One document-upload action accepts either one file or several files. Every file becomes an independent document with its own extraction, failure, and review state. A failed file does not block its siblings.

The product does not create a separate batch resource or require batch listing and retrieval routes. The upload response is the list of documents created by that request.

---

# 52. Model strategy

Prefer a lightweight model.

This is deliberate.

The project should demonstrate that a thoughtfully designed extraction pipeline doesn't require the most capable model for every operation.

The architecture saves model reasoning for situations requiring semantics. For JSON, one document-level semantic investigation should recover related facts together; deterministic profiling, validation, and calculation should minimize unnecessary calls without reusing a prior supplier mapping.

---

# 53. Evaluation framework

Evaluation should be a first-class component.

Create ground-truth expected values for the supplied documents.

Evaluate at field level.

Potential measures:

```text
exact match
numeric tolerance
normalized string match
field precision
field recall
null correctness
correction handling
OCR degradation behavior
```

Special evaluation cases should include:

### Clean JSON

Can the system correctly map different JSON shapes?

### Pack-derived pricing

Can it derive unit prices correctly?

### Price tiers

Does it preserve every tier?

### Email correction

Does the corrected value win?

### Images

Does the system reduce confidence rather than hallucinate when content is unreadable?

### Combination medicines

Are ingredients and strengths kept correctly paired?

---

# 54. Cost evaluation

Track model usage:

```text
document
model
operation
input tokens
output tokens
duration
estimated cost
```

For JSON, telemetry records the semantic extraction call and its source-validation retry, if any. It never stores a schema fingerprint or reusable mapping.

---

# 55. Latency evaluation

Track time spent in:

```text
parsing
OCR
PII processing
LLM extraction
normalization
validation
total processing time
```

This will show where the actual bottlenecks are.

---

# 56. Production considerations

The take-home remains local, but the design should acknowledge what changes in a real deployment.

## Database

SQLite would likely be replaced with a database appropriate for concurrent distributed application workloads.

The take-home does **not** deploy one.

## Background-processing system

The take-home uses API-owned Python background tasks and does not depend on Huey. This is intentionally a single-process convenience, not a durable distributed job system. At production scale, introduce a managed queue and worker service only with explicit timeouts, idempotency, retry policy, dead-letter handling, stale-job recovery, and operational observability.

## Object storage

Raw documents would normally live in encrypted object storage rather than local disk.

## OCR

Modal workers could scale independently according to OCR demand.

## LLM provider

Production use should require suitable contractual data handling, retention and privacy terms.

---

# 57. Security and regulated-data considerations

A production version should include:

```text
encryption at rest
encryption in transit
role-based access
document retention rules
audit logging
secret management
PII minimization
model-provider data policies
regional processing requirements where applicable
```

Raw source documents should have tighter access control than normalized commercial records.

---

# 58. CI/CD

The repository should support reproducible setup and testing.

Pipeline should conceptually include:

```text
lint
type checks
unit tests
extraction evaluations
build
```

Important tests include:

- parser tests
- JSON semantic extraction and source-validation tests
- deterministic calculation tests
- validation tests
- PII redaction tests
- sample-document regression tests

Model-dependent evaluations shouldn't make every normal CI run expensive.

A small deterministic fixture set can run continuously, with fuller LLM evaluations run separately.

---

# 59. Repository structure

The backend uses a shallow structure with names that describe the code directly:

```text
axmed-document-intelligence/

├── backend/
│ ├── app/
│ │ ├── api.py
│ │ ├── config.py
│ │ ├── database.py
│ │ ├── documents.py
│ │ ├── events.py
│ │ ├── evaluations.py
│ │ ├── logging.py
│ │ ├── models.py
│ │ ├── extraction/
│ │ └── security/
│ │
│ └── tests/
│
├── frontend/
│
├── evals/
│ ├── fixtures/
│ ├── ground_truth/
│ └── reports/
│
├── sample_documents/
│
├── output/
│
├── README.md
└── AGENT_CONVERSATION.md
```

This is directional, not a requirement to split every concept into its own package before it's necessary.

---

# 60. Deliverables

The final repository should contain:

### Runnable application

FastAPI backend and Vue frontend.

### Supplied documents

Allowed because the assignment states the corpus is synthetic.

### Output table

Extracted line-item data suitable for review.

### Confidence and source information

Required for every record.

### Agent-generated planning summary

The assignment explicitly asks for an LLM/Claude-generated Markdown file describing the conversation used to plan and execute the work and highlighting the candidate's role.

### Write-up

Cover:

- architecture
- parsing strategy
- OCR
- structured vs natural-language handling
- uncertainty
- human review
- cost
- latency
- privacy
- production architecture
- CI/CD
- limitations
- improved data model

---

# 61. What we're deliberately not doing

A few things should stay out unless they prove necessary.

**No model-directed routing for a known ingestion path.**

Media detection, parser selection, safety gates, persistence, commercial rules, and review transitions remain explicit application control flow. Adaptive investigation is limited to semantic ambiguity inside extraction.

**No separate model call for every JSON field.**

One document-level investigation recovers related facts together, while deterministic path/value validation and commercial calculations remain ordinary software.

**No OCR of every PDF.**

Use LiteParse first and escalate only when needed.

**No attempt to manufacture certainty.**

Unreadable values remain unreadable.

**No external database or Redis requirement for the take-home.**

SQLite plus API-owned Python background tasks gives us the local architecture we want for now.

**No medicine-catalogue RAG layer.**

This take-home does not require building a medicine catalogue or matching extracted products against one.

Without a trusted reference corpus, adding catalogue retrieval would solve a different problem and add complexity without improving the core quotation-extraction task.

Instead, each JSON source is profiled and interpreted independently. Its extracted facts are JSONPath-validated, normalized only where certain, and otherwise preserved without a reusable schema interpretation.

---


# 62. Core technical thesis

The interesting part of the submission isn't that an LLM can turn a quotation into JSON.

The system should demonstrate something stronger:

```text
Messy supplier input
 ↓
Use structure when structure exists
 ↓
Investigate each document against source-grounded target-field knowledge
 ↓
Repair only claims rejected by deterministic validation
 ↓
Preserve source evidence
 ↓
Derive comparable commercial information deterministically
 ↓
Expose uncertainty instead of hiding it
 ↓
Let a human make the final decision
```

Source-grounded extraction is the piece to emphasize most. The system must preserve correct facts even when a source's structure does not cleanly fit the canonical quotation.

LLM interpretation is scoped to each source. Cost and latency can be improved later with a separately evaluated optimization, but not by treating a prior source-schema interpretation as truth for a new document.

That's a much more interesting document-intelligence system than `upload → LLM → CSV`.
