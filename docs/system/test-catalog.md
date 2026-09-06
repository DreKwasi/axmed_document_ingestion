# Test Catalog

> Purpose: inventory meaningful automated tests and the behavior each protects.
> Status: Slice 1 baseline — focused backend and Vue tests exist; expand with every behavioral slice.
> Update in the same change whenever tests are added, removed, renamed, or materially repurposed.
> Owner persona: quality engineer.
> Related: `docs/system/testing.md`, `docs/system/false-confidence-audits.md`.
> Search terms: test catalog, coverage, journey, regression, owner.
> Each entry describes what could break, not merely the test filename.

| Test / suite | Layer | Protects | Known limitations | Worksheet |
| --- | --- | --- | --- | --- |
| `backend/tests/test_schema_learning.py` | API/integration | cold mapping proposal, human confirmation, trusted warm cache, schema-version isolation, reviewable schema conflict, receipt identity, malformed mapping failure, JSON validation | recorded mapper only; live model comes later | DI-01 |
| `backend/tests/test_canonical_nulls.py` | unit | a missing required source value is preserved as `null` and produces an explicit review issue | field criticality is declared by the mapping fixture; more corpus cases needed | DI-01 |
| `backend/tests/test_migrations.py` | integration | fresh application startup applies the checked-in Alembic revision and versioned mapping uniqueness | legacy pre-Alembic local databases are baselined only when their complete Slice 1 table set exists | DI-01 |
| `backend/tests/test_evaluations.py` | API/integration | SQLite-backed evaluation case/run/result, cold/warm mapping contract, actual zero warm tokens/cost, and rubric scores | one initial recorded golden case; grow to MVE set | DI-01 |
| `frontend/src/App.spec.ts` | component | evaluation lab displays persisted rubric and requests a new API evaluation; new-schema state displays and confirms the human mapping checkpoint | browser upload/review journey needs Playwright | DI-01 |
| `backend/tests/test_commercial_review.py` | API/integration | quoted pack-price preservation, deterministic unit-price derivation, source-file retrieval, commercial validation, correction evidence/audit/learning job, idempotency, and stale-review conflict | richer tier/discount fixtures arrive with their source formats; queued learning executes after the PII-safe worker exists | DI-02 |
| `backend/tests/test_commercial_rules.py` | unit | date validity, percentage bounds, non-overlapping tiers, and compatible quoted-quantity/MOQ checks at the deterministic validation seam | only rules with a canonical source field are added; source aliases stay out of this suite | DI-02 |
| `frontend/src/App.spec.ts` | component | compact extracted-offer table, table-contained review controls, mapping confirmation, per-line typed correction command, and retention of every selected upload | browser batch journey remains to be added; component test validates selection retention | DI-02 |
| `frontend/e2e/review.spec.ts` | end-to-end | isolated API/web startup, mapping confirmation, price correction/derivation, and explicit approval | one JSON fixture; batch and non-JSON journeys arrive with their parser slices | DI-02 |
