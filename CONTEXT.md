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
