# Supplier Document Intelligence Context

## Ubiquitous language

- **Extraction availability:** source fields are persisted when present; absence alone is neither a confidence score nor a review gate.
- **Confidence:** categorical assessment of one persisted extracted field: `High`, `Medium`, or `Low`, with an observable reason; it is not a percentage or a completeness score.
- **Review status:** human approval lifecycle for a successful source: `pending_review`, `approved`, or `rejected`.
- **Pending review:** every successful extraction waits for human review, regardless of confidence.
- **Approved:** explicitly accepted by a human reviewer.
- **Corrected:** an audited reviewer action that changes persisted field values; the source remains pending until it is explicitly approved or rejected.
- **Rejected:** reviewer declined the source using a structured rejection reason and optional note.
- **Review queue:** default list containing all `pending_review` records; confidence and review issues prioritize attention within it.
- **Dosage form:** the canonical product form, such as tablet, syrup, or suspension. Route is not a separate canonical product field.
- **Delivery lead-time range:** the stated shipment/transit duration for a source or its applicable line items, preserved as a minimum and maximum number of days when the source gives a range.
- **HS codes:** document-level customs classification codes for the shipment. They are not product therapeutic classifications and are not represented on individual products unless the source explicitly scopes them that way.
