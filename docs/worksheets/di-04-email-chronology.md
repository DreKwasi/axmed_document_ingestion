# Worksheet: DI-04 email chronology

> Purpose: parse supplier email deterministically before redacted semantic reconciliation.
> Scope: MIME-only intake, chronology, supersession evidence, and privacy-safe model context.
> Status: semantic extraction implemented; resolver configuration remains environment-owned.
> Dependencies: DI-03 durable learning/events.
> Source requirements: PRD v2 and Slice 4 in `docs/plans/implementation-plan.md`.
> Privacy rule: do not render HTML or store/send contact details to a resolver.
> No Modal deployment is involved.

## Work log

- 2026-09-06: Added `app.email_parser.parse_email`, which uses Python's MIME parser, selects deduplicated plain-text parts, redacts contact identifiers, and never renders HTML.
- 2026-09-06: Added an executable Novara fixture test proving the P.S. correction text survives while the sender email and HTML do not.
- 2026-09-06: `.eml` uploads now persist a source document, redacted parse context, durable extraction record, and `email_extraction_queued` event. Huey executes the configured semantic resolver through a structured canonical-quotation contract; completed output is commercially validated and enters human review.
- 2026-09-06: Model invocation audit rows are linked to email extraction jobs. Without a configured resolver, the job remains visibly awaiting configuration rather than producing a made-up quotation.

## Remaining

- Configure a live semantic resolver before enabling autonomous email extraction outside local development.
- Add malformed-response, queue-consumer, provenance, browser, and evaluation coverage as the remaining document-format slices land.
