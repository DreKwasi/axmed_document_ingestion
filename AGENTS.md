# Agent Router

> Purpose: route each request to the smallest useful workflow, docs, tools, and validations.
> Read this file first. Read the first seven lines of every relevant system document before deeper reading.
> System docs live in `docs/system/`; keep them correct whenever code, behavior, tests, or operations change.
> Do not claim work is complete without running the application and the relevant automated checks.
> Record every implementation session in `docs/worksheets/` and commit it with the work when Git is available.
> Add concise end-of-session feedback to `docs/agent-feedback.md`.

## Route the request

| Situation | Read / use first | Then run |
| --- | --- | --- |
| Any implementation | `@AGENT_WORKFLOW.md`, `docs/system/coding-conventions.md` | `bin/agent-validate targeted` |
| New feature or design | `docs/system/architecture.md`, `docs/system/testing.md` | app + targeted tests |
| Product requirements or scope | `docs/product/axmed_document_intelligence_prd.md`, `docs/plans/implementation-plan.md` | update the affected plan/system docs |
| Bug or regression | `docs/system/testing.md`, `docs/system/test-catalog.md` | reproduce, fix, regression test |
| UI work | `docs/system/visual-regression.md`, `docs/system/testing.md` | app + visual checks |
| Performance-sensitive work | `docs/system/performance.md` | baseline and compare |
| Security/domain-sensitive work | `docs/system/agent-review.md` plus the relevant system doc | persona review |
| Tooling, hooks, or repair automation | `docs/system/tooling.md` | `bin/agent-lint --fix` |
| Autonomous/night shift | `.codex/skills/autonomous-shift/SKILL.md` | full validation before stopping |
| Review, handoff, or sweep | `docs/system/agent-review.md` | `bin/agent-sweep` |

## Operating rules

1. Find relevant docs with `rg -n "keyword" docs/system`; their first seven lines are searchable summaries.
2. Start or run the app yourself before changing app behavior. Exercise the path you changed; screenshots are evidence for UI work.
3. Write a focused test before considering a behavior fixed. Keep `docs/system/test-catalog.md` synchronized with added, removed, or materially changed tests.
4. Run `bin/agent-validate targeted` during implementation and `bin/agent-validate full` at wrap-up. Fix failures; never silence them without documenting why.
5. Use `bin/agent-review <stage>` at research, plan, implementation, and wrap-up. Seek an independent reviewer/model when access exists; otherwise record the limitation and use distinct personas.
6. Update the system docs owned by the persona that changed the system. Every system doc begins with a seven-line, greppable summary.
7. Create a worksheet from `docs/worksheets/TEMPLATE.md`; commit it with its associated changes and tag its final commit as `worksheet/<name>` when Git is configured.
8. Add one actionable observation to `docs/agent-feedback.md` at the end of a session. Periodically run `bin/agent-sweep` and convert recurring feedback into workflow improvements.

## Local capabilities

- Installed reusable skills include: `implement`, `diagnosing-bugs`, `tdd`, `code-review`, `web-perf`, `frontend-design`, `visualize`, and `skill-creator`.
- `bin/agent-review` is a portable review dispatcher. Configure external CLIs only when they are available; it never invents reviewer access.
- `bin/agent-validate` detects common JavaScript/Python tooling. Extend it when this repository chooses a stack.

## Source of truth

`TODOS.md` is the local task queue. Do not start unqueued autonomous work unless the user requested it. Architecture, test inventory, conventions, reviews, performance, and visual baselines are documented in `docs/system/`.
