# Supplier Document Intelligence Context

## Ubiquitous language

- **Extraction coverage:** count of expected key fields recovered; it says nothing about correctness.
- **Field reliability:** categorical assessment of one persisted field: `high`, `medium`, `low`, or `not_extracted`, with an observable reason.
- **System decision:** automated routing outcome after extraction: `auto_accepted` or `needs_review`.
- **Human outcome:** reviewer outcome, independent from system decision: `unreviewed`, `approved`, `corrected`, or `rejected`.
- **Auto-accepted:** trusted by policy without human inspection; never synonymous with approved.
- **Approved:** explicitly accepted by a human reviewer.
- **Corrected:** reviewer changed persisted field values; the prior and replacement values remain auditable.
- **Rejected:** reviewer declined the source using a structured rejection reason and optional note.
- **Exception queue:** default review list containing `needs_review` records, not all successful extractions.
