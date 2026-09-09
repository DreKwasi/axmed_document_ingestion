# Worksheet: test-suite-pruning

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

Reduce the automated-suite surface by removing redundant or stale tests while retaining meaningful behavioral coverage for supported flows. The focused and full validation commands must pass, and the test catalog must describe the remaining suite accurately.

## Context and constraints

The suite currently has 169 test declarations across backend unit/integration tests and frontend component/E2E tests (6,031 lines). Existing uncommitted user changes are out of scope and must be preserved.

## Plan

Inventory overlapping test cases, retain one high-signal behavioral test per seam, remove superseded low-value variants, update the catalog, then validate the application and suites.

## Work log and evidence

- 2026-09-09: Read `AGENTS.md`, workflow, coding conventions, testing strategy, test catalog, task queue, and review protocol. Research review reported no independent provider is configured; isolated persona passes will be recorded below.

## Tests, app run, and validation

## Review findings and resolutions

## Docs updated

## Handoff / remaining work

## Final commit and tag
