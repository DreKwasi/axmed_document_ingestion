# Worksheet: normalized-unit-price-fallback

> Created: 2026-09-07
> Status: complete
> Scope: derive a normalized price from an already unit-based quoted price when no pack-price derivation applies.

## Goal

When a supplier quote is already expressed per item (for example, USD per tablet), expose that same amount as the normalized price. Continue to calculate a unit price from pack price only when the pack contents are known.

## Evidence and constraints

- `commercial_rules._price_and_pack` currently returns before populating `normalized_price` unless `pack_price` exists.
- The source UOM remains preserved as the quoted commercial basis. This change must not invent a UOM or use pack metadata that is absent.
- Existing worktree changes predate this session and are preserved.
- Reviews: research and plan used the local persona checklist because no independent provider is configured.

## Plan and acceptance checks

1. Add a unit-price fallback that copies an explicit quoted amount and UOM when there is no pack price.
2. Add a focused backend regression test for the fallback and run it before/after the change.
3. Run targeted validation, start the app, and exercise the product drawer state.
4. Update test inventory, feedback, review records, and run full validation.

## Session log

- 2026-09-07: Began from the user-confirmed rule: already-unit-based quotes should repeat as normalized price; pack prices require known units per pack.
- 2026-09-07: Added the fallback plus a red-to-green regression test. The scope deliberately excludes a migration: existing stored records remain unchanged until reprocessed or corrected.
- 2026-09-07: UI path exercised against the running application. The existing Farmaceutica source correctly shows its quoted per-tablet price but predates this calculation, so it remains blank without a backfill; the automated regression covers new processing.
- 2026-09-07: Implementation review used local quality, code-quality, domain, and UX personas because no independent reviewer is configured. The only review finding was the unnecessary backfill migration; removed at user direction.
- 2026-09-07: Verification: focused regression passed; frontend lint and component tests passed; full validation passed frontend lint/tests/build and both Playwright journeys. Backend validation ran 88 tests successfully but has three pre-existing migration-head assertion failures because the uncommitted `20260907_18_supply_ranges_and_product_schema.py` advances Alembic while `test_migrations.py` still expects `20260907_17`. No commit was made because the shared worktree contains unrelated in-progress changes.
