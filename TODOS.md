# Task Queue

> Purpose: local, grep-friendly task queue for agents and humans.
> Keep tasks small enough to finish and verify in one worksheet where possible.
> Every task states acceptance checks and the system docs likely to change.
> Do not silently remove completed work: mark it done with a link to its worksheet/commit.
> Autonomous agents select only explicitly marked `ready` tasks.
> Review this queue during session orientation and periodic sweeps.

## Ready

- [ ] **Bootstrap application stack** — choose the runtime, add a runnable minimal app, and configure its test/lint commands. Acceptance: `bin/agent-validate full` runs meaningful checks. Docs: architecture, testing, test catalog.

## Backlog

- [ ] **Choose visual regression harness** — select Playwright or equivalent once the app stack exists. Acceptance: a deterministic baseline, comparison, and documented update path. Docs: visual regression, testing.
- [ ] **Choose benchmark harness** — add representative performance scenarios and enforce a regression budget. Docs: performance.
- [ ] **Configure independent review providers** — set `AGENT_REVIEW_COMMAND` and, if desired, `AGENT_FIX_COMMAND` in the developer environment. Docs: agent review, tooling.
