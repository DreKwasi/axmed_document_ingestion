# Axmed Document Intelligence Agent

## Product Requirements Document

**Project:** Supplier Document Intelligence  
**Context:** Axmed AI Engineer Take-Home Assignment  
**Primary stack:** Python / FastAPI + Vue 3  
**Document status:** Working implementation specification

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

The pipeline should become increasingly deterministic as previously encountered supplier schemas are seen again.

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

Zenith includes product route, manufacturer, country of origin, regulatory qualification, cold-chain requirements, HS codes and ATC codes alongside commercial data.

The canonical model therefore needs to represent both the medicine and the commercial context around its price.

---

# 5. High-level architecture

```text
┌──────────────────────────────┐
│            Vue 3             │
│                              │
│ Upload                       │
│ Processing state             │
│ Review                       │
│ Source/evidence inspection   │
└──────────────┬───────────────┘
               │
          REST + SSE
               │
               ▼
┌──────────────────────────────┐
│           FastAPI            │
│                              │
│ Ingestion                    │
│ Fast deterministic parsing   │
│ Workflow coordination        │
│ Human-review operations      │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│    Synchronous Fast Path     │
│                              │
│ File validation              │
│ Type detection               │
│ JSON parsing                 │
│ Email parsing                │
│ LiteParse PDF parsing        │
│ Parse-quality assessment     │
│ OCR requirement detection    │
│ Parsed artifact persistence  │
└──────────────┬───────────────┘
               │
               │ enqueue
               ▼
┌──────────────────────────────┐
│             Huey             │
│                              │
│ Durable async jobs           │
│ Worker execution             │
│ Retry handling               │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│     Async Intelligence       │
│                              │
│ OCR escalation               │
│ PII detection/redaction      │
│ Schema recognition           │
│ Semantic extraction          │
│ Reconciliation              │
│ Normalization                │
│ Validation                   │
│ Confidence scoring           │
│ Provenance capture           │
└──────┬────────────┬──────────┘
       │            │
       ▼            ▼
┌─────────────┐ ┌──────────────────┐
│ PaddleOCR   │ │ Microsoft       │
│ on Modal    │ │ Presidio        │
│             │ │                  │
│ Images      │ │ PII detection    │
│ Bad pages   │ │ Redaction        │
└──────┬──────┘ └────────┬─────────┘
       │                 │
       └────────┬────────┘
                ▼
       ┌────────────────┐
       │   LangChain    │
       │                │
       │ Lightweight LLM│
       │ Structured      │
       │ extraction      │
       └────────┬───────┘
                ▼
┌──────────────────────────────┐
│            SQLite            │
│                              │
│ Documents                    │
│ Parsed representations       │
│ Schema mapping memory        │
│ Quotation data               │
│ Derived values               │
│ Confidence                   │
│ Processing events            │
│ Review state                 │
│ Provenance                   │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│        Human Review          │
│                              │
│ Review                       │
│ Correct                      │
│ Approve                      │
│ Reject                       │
└──────────────────────────────┘
```

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

Application state lives locally.

Huey's internal queue should use a separate SQLite database so queue state and application data aren't mixed.

Conceptually:

```text
data/
├── app.db
└── tasks.db
```

## Background processing

**Huey with SqliteHuey**

Huey provides a real worker boundary without requiring an additional infrastructure service.

The worker handles operations that may be:

- slow
- remote
- model-dependent
- retryable
- computationally expensive

A document, rather than an entire folder, should generally be the useful unit of asynchronous work.

That means one bad scan doesn't prevent unrelated clean documents from completing.

---

# 7. Sync vs async processing

We don't want to send everything into the worker simply because workers exist.

## Synchronous path

The normal server process handles operations expected to complete quickly and predictably:

```text
Upload
 ↓
Validate
 ↓
Detect document type
 ↓
Basic deterministic parsing
 ↓
Assess parse quality
 ↓
Persist parsed representation
 ↓
Queue heavy processing
 ↓
Respond
```

Examples:

### JSON

Parse using Python's JSON tooling.

### Email

Parse MIME structure, headers and body deterministically.

### PDF

Use LiteParse to recover native document structure.

### Images

Perform lightweight file validation and metadata inspection.

---

# 8. Async path

Huey handles operations with unpredictable runtime or external dependencies.

```text
Parsed document
      ↓
OCR if necessary
      ↓
PII scan/redaction
      ↓
Schema mapping
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

The Huey worker does not communicate directly with browser connections.

Instead:

```text
Huey
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

This keeps the worker independent from frontend connection state.

If the browser disconnects, document processing continues normally.

---

# 10. PDF processing

## Primary parser: LiteParse

LiteParse handles digitally generated PDFs.

Its responsibilities include:

- text extraction
- structural extraction
- table recovery
- reading order
- identifying pages likely to require OCR

The objective is to avoid OCR when usable document information already exists.

---

# 11. OCR architecture

**PaddleOCR deployed on Modal**

OCR is an escalation path.

```text
PDF
 ↓
LiteParse
 ↓
quality assessment
 ├── good → continue
 │
 └── poor page(s)
          ↓
       PaddleOCR
```

Images go directly toward the OCR path when necessary.

Only relevant pages should be escalated when a mixed PDF contains both clean and scanned content.

Modal is appropriate because OCR inference can scale separately from FastAPI and the implementation already has familiarity with deploying PaddleOCR there.

---

# 12. PII handling

PII detection occurs before document content is sent to the LLM.

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

# 13. Logging and sensitive information

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

# 14. Canonical quotation model

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

# 15. Quotation-level schema

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

# 16. Supplier schema

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

# 17. Commercial terms

```json
{
  "currency": null,
  "incoterm": null,
  "incoterm_named_place": null,
  "payment_terms": null,
  "freight_included": null,
  "insurance_included": null,
  "tax_included": null,
  "price_basis": null
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

# 18. Product identity

```json
{
  "trade_name": null,
  "inn": [],
  "strength": [],
  "dosage_form": null,
  "route": null,
  "manufacturer": null,
  "country_of_origin": null
}
```

`dosage_form` is the core comparable form (for example, `tablet`, `syrup`, or `suspension`). Preserve qualifying details such as `film-coated`, `chewable`, and `pressurised inhalation` in `packaging.presentation`.

---

# 19. Structured strength

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

# 20. Packaging

```json
{
  "description": null,
  "presentation": null,
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

# 21. Quantity

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

# 22. Pricing

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

# 23. Quoted price

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

# 24. Price normalization

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

---

# 25. Price tiers

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

# 26. Discounts and adjustments

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

# 27. Supply information

```json
{
  "lead_time_days": null,
  "shelf_life_months": null,
  "minimum_remaining_shelf_life_percent": null,
  "storage_conditions": null,
  "cold_chain_required": null
}
```

This becomes particularly relevant for temperature-sensitive products such as insulin and oxytocin.

---

# 28. Regulatory information

```json
{
  "who_prequalified": null,
  "who_pq_reference": null,
  "registered_markets": [],
  "registration_reference": null,
  "regulatory_status": null,
  "hs_code": null,
  "atc_code": null
}
```

This isn't part of the minimum take-home schema, but the supplied documents clearly contain this information.

The architecture should allow extraction even if the first review table exposes only a subset.

---

# 29. Source and provenance

Each resulting line must be traceable back to its source.

At minimum:

```json
{
  "document_name": null,
  "document_format": null
}
```

Internally, provenance should be richer.

For a field:

```json
{
  "canonical_field": "pricing.quoted_price.amount",
  "value": 0.134,
  "source_document": "RE_RFQ-2026-0244_Novara_quotation.eml",
  "source_location": "P.S. correction",
  "extraction_method": "llm",
  "confidence": 0.99
}
```

---

# 30. Extracted vs derived values

This distinction should exist throughout the system.

Possible origins:

```text
source
deterministic_mapping
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

# 31. JSON schema recognition

JSON should use a progressive field-mapping system: simple and known cases should be handled cheaply and deterministically, while ambiguous cases should receive progressively stronger interpretation.

Fuzzy similarity should not be treated as authoritative. It is only used to generate plausible candidates for unresolved fields.

```text
Incoming JSON
     ↓
Flatten / discover paths
     ↓
Normalize key names
     ↓
Look up known supplier/schema mappings
     ↓
Apply deterministic canonical matches
     ↓
Apply small global alias set
     ↓
Generate fuzzy candidates for unresolved fields
     ↓
LLM resolves ambiguous mappings using field context
     ↓
Validate
     ↓
Human correction where required
     ↓
Persist successful mappings
```

The key principle is:

```text
Known mapping
→ deterministic reuse

Obvious canonical field
→ deterministic mapping

Near-match field name
→ fuzzy candidates only

Ambiguous/new field
→ LLM resolution

Low-confidence result
→ human review
```

This keeps the LLM focused on semantic ambiguity rather than repeatedly rediscovering mappings the system already understands.

---

# 32. Key normalization

Supplier naming conventions vary:

```text
pricePerPack
price_per_pack
PRICE_PER_PACK
Price Per Pack
```

Normalize these into a comparable representation before mapping.

This is cheap and deterministic.

---

# 33. Small global alias layer

Maintain only a small set of obvious universal aliases.

Example:

```text
generic_name
active_ingredient
active_moiety
→ product.inn
```

The system should not depend on maintaining an enormous global dictionary.

A large alias registry quickly becomes brittle and supplier-specific. The goal is to handle common conventions deterministically while allowing the mapping memory and LLM resolver to absorb the long tail.

---

# 34. Fuzzy matching as candidate generation

Fuzzy matching should not automatically accept a canonical mapping on first encounter.

Use a lightweight technique such as RapidFuzz only to narrow the candidate space for fields that have not already been resolved by exact matches, known schema mappings, or the small global alias set.

For example:

```text
source field:
min_order_packs

possible canonical candidates:
1. quantity.minimum_order_quantity
2. packaging.units_per_pack
3. quantity.quoted_quantity
```

The fuzzy score is not treated as proof.

Instead, the LLM receives:

```text
source field
sample value
nearby fields
supplier/schema context
top candidate mappings
```

and chooses the most plausible canonical target.

If the result remains uncertain, the field is flagged for human review.

The project should not rely on a hard rule such as:

```text
score > 92
→ accept
```

unless later evaluation shows that a threshold is safe for a narrowly defined field class.

---

# 35. Supplier-specific schema memory

SQLite stores successful mappings.

Conceptually:

```text
schema_mapping

supplier
source_system
schema_version
schema_fingerprint

source_path
canonical_field

mapping_method
confidence

times_seen
times_confirmed

human_verified

created_at
last_seen_at
```

Example:

```text
SanovaERP
2.4.1
offer.products[].commercials.price_per_pack
→ pricing.quoted_price.amount
```

---

# 36. Schema fingerprinting

Not every supplier provides an explicit schema version.

Generate a fingerprint from normalized JSON paths.

For example:

```text
offer.products[].commercials.price_per_pack
offer.products[].commercials.minimum_order_quantity_packs
offer.products[].packaging.units_per_pack
offer.products[].generic_name
```

Normalize and hash the structure.

```text
schema_fingerprint =
SHA256(normalized_paths)
```

If the supplier silently changes its ERP export structure, the fingerprint changes and the system can re-evaluate mappings.

---

# 37. Learning from uploads

The model itself isn't being retrained.

The application builds **mapping memory**.

```text
First encounter
      ↓
unknown fields
      ↓
LLM-assisted mapping
      ↓
validation / review
      ↓
persist mapping

Future encounter
      ↓
mapping found
      ↓
deterministic extraction
```

This has a major cost consequence.

The LLM increasingly handles only novelty.

---

# 38. Human corrections improve schema recognition

Suppose the system maps:

```text
order_qty
→ minimum_order_quantity
```

but a reviewer corrects it to:

```text
order_qty
→ quoted_quantity
```

That correction should update the supplier/schema mapping.

Human review therefore improves future extraction.

---

# 39. Mapping trust

A mapping shouldn't automatically become permanently trusted because the LLM used it once.

Track:

```text
times_seen
times_confirmed
human_verified
conflict_count
last_seen
schema_fingerprint
```

Potential policy:

```text
Human verified
→ trusted deterministic reuse

Repeated model mapping + successful validation
→ reusable with high confidence

Changed fingerprint
→ re-evaluate
```

---

# 40. Deterministic derived calculations

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

# 41. Deterministic validation

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

# 42. LLM responsibilities

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

# 43. Email extraction

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

# 44. Confidence model

Do not rely solely on:

```text
LLM confidence = 0.94
```

Confidence should combine observable signals.

Examples of positive signals:

```text
direct JSON field
exact known mapping
human-verified schema mapping
native PDF text
successful arithmetic validation
multiple agreeing signals
```

Negative signals:

```text
OCR required
low OCR confidence
ambiguous field mapping
derived from incomplete packaging information
conflicting prices
missing unit
unresolved Incoterm context
validation failure
```

Field-level confidence is preferable to one document-wide score.

---

# 45. Review status

Useful states might conceptually include:

```text
pending
processing
needs_review
approved
corrected
rejected
failed
```

Exact implementation naming can be decided during development.

---

# 46. Review experience

The user should be able to quickly answer:

> What did the system extract?

> What is uncertain?

> Where did this value come from?

> Did the system calculate this or did the supplier actually say it?

The interface should prioritize suspicious fields.

Example:

| Product | Quantity | Price | Basis | Confidence | Issue |
|---|---:|---:|---|---:|---|
| Azimax 250 | — | €0.134 | tablet | High | corrected in email |
| Sanotri-TLD | — | €0.035 | tablet | High | derived from pack price |
| Scan item | 50,000 | ? | pack | Low | glare obscures price |

The reviewer shouldn't have to manually inspect every field when 95% of the extraction is straightforward.

---

# 47. Evidence view

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

# 48. Processing events

Maintain a lightweight processing-event history.

Conceptually:

```text
document_received
document_parsed
ocr_required
ocr_started
ocr_completed
pii_redacted
schema_mapping_started
extraction_started
validation_completed
review_required
processing_completed
processing_failed
```

These events support both SSE updates and operational debugging.

---

# 49. Failure handling

Failures should be explicit.

### Unsupported file

Reject during intake.

### Corrupted PDF

Fail during synchronous parsing where possible.

### OCR service unavailable

Worker retries.

If retry budget is exhausted:

```text
failed
reason = OCR unavailable
```

### LLM returns invalid structure

Retry structured extraction where appropriate.

Then fail or request review rather than accepting malformed data.

### Unreadable field

Store null and flag.

---

# 50. File batches

A folder upload is represented conceptually as a batch containing documents.

```text
Batch
 ├── Document
 ├── Document
 ├── Document
 └── Document
```

Processing occurs independently per document.

Batch progress is aggregated from child documents.

This allows:

```text
997 completed
2 require review
1 failed
```

without treating the whole batch as failed.

---

# 51. Model strategy

Prefer a lightweight model.

This is deliberate.

The project should demonstrate that a thoughtfully designed extraction pipeline doesn't require the most capable model for every operation.

The architecture saves model reasoning for situations requiring semantics.

Clean JSON should trend toward near-zero LLM usage as mappings accumulate.

---

# 52. Evaluation framework

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

# 53. Cost evaluation

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

Then demonstrate the effect of schema memory.

For example:

```text
First Sanova schema encounter
→ LLM schema mapping

Second identical schema
→ cached mapping
→ no schema-mapping LLM call
```

This is a meaningful product characteristic rather than just a benchmark.

---

# 54. Latency evaluation

Track time spent in:

```text
parsing
OCR
PII processing
LLM extraction
normalization
validation
total worker time
```

This will show where the actual bottlenecks are.

---

# 55. Production considerations

The take-home remains local, but the design should acknowledge what changes in a real deployment.

## Database

SQLite would likely be replaced with a database appropriate for concurrent distributed application workloads.

The take-home does **not** deploy one.

## Worker system

Huey is appropriate for the constrained local implementation.

At larger distributed scale, queue architecture would be revisited based on throughput, retry guarantees and deployment topology.

## Object storage

Raw documents would normally live in encrypted object storage rather than local disk.

## OCR

Modal workers could scale independently according to OCR demand.

## LLM provider

Production use should require suitable contractual data handling, retention and privacy terms.

---

# 56. Security and regulated-data considerations

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

# 57. CI/CD

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
- schema mapping tests
- deterministic calculation tests
- validation tests
- PII redaction tests
- sample-document regression tests

Model-dependent evaluations shouldn't make every normal CI run expensive.

A small deterministic fixture set can run continuously, with fuller LLM evaluations run separately.

---

# 58. Repository structure

A sensible high-level repository might be:

```text
axmed-document-intelligence/

├── backend/
│   ├── app/
│   │   ├── ingestion/
│   │   ├── parsers/
│   │   ├── ocr/
│   │   ├── privacy/
│   │   ├── extraction/
│   │   ├── schema_mapping/
│   │   ├── normalization/
│   │   ├── validation/
│   │   ├── confidence/
│   │   ├── provenance/
│   │   ├── review/
│   │   ├── workers/
│   │   └── models/
│   │
│   └── tests/
│
├── frontend/
│
├── backend/evals/
│   ├── fixtures/
│   ├── ground_truth/
│   └── reports/
│
├── sample_documents/
│
├── output/
│
├── README.md
├── WRITEUP.md
└── AGENT_CONVERSATION.md
```

This is directional, not a requirement to split every concept into its own package before it's necessary.

---

# 59. Deliverables

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

# 60. What we're deliberately not doing

A few things should stay out unless they prove necessary.

**No LangGraph just to call this an agent.**

The workflow is sufficiently known that a pipeline is easier to understand and test.

**No LLM on every JSON field.**

Schema memory and deterministic calculations should steadily reduce model usage.

**No OCR of every PDF.**

Use LiteParse first and escalate only when needed.

**No attempt to manufacture certainty.**

Unreadable values remain unreadable.

**No external database or Redis requirement for the take-home.**

SQLite + Huey gives us the local architecture we want.

**No medicine-catalogue RAG layer.**

This take-home does not require building a medicine catalogue or matching extracted products against one.

Without a trusted reference corpus, adding catalogue retrieval would solve a different problem and add complexity without improving the core quotation-extraction task.

Instead, schema recognition follows a layered approach:

```text
known mapping
→ deterministic reuse

similar unknown field
→ fuzzy candidate generation

semantic ambiguity
→ LLM resolution

reviewer correction
→ stored mapping memory
```

The retrieval-like memory in this project is the SQLite-backed supplier/schema mapping store, not a medicine catalogue.

---

# 61. Core technical thesis

The interesting part of the submission isn't that an LLM can turn a quotation into JSON.

The system should demonstrate something stronger:

```text
Messy supplier input
        ↓
Use structure when structure exists
        ↓
Remember supplier schemas we've already understood
        ↓
Escalate only ambiguous content to AI
        ↓
Preserve source evidence
        ↓
Derive comparable commercial information deterministically
        ↓
Expose uncertainty instead of hiding it
        ↓
Let a human make the final decision
```

The schema-mapping memory is one of the pieces to emphasize most.

On the first encounter with a supplier export, the system may need meaningful LLM assistance. Once that schema has been understood and validated, subsequent documents increasingly become ordinary deterministic data processing.

So accuracy should improve while latency, token consumption, and model cost fall.

That's a much more interesting document-intelligence system than `upload → LLM → CSV`.
