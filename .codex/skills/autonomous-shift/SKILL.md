---
name: autonomous-shift
description: Execute queued repository work autonomously with durable handoffs, staged review, live app verification, and full end-of-shift validation.
---

# Autonomous Shift

Use this skill for explicitly requested unattended work on ready tasks in `TODOS.md`. It does not authorize production changes, external messages, or work not explicitly queued.

1. Read `AGENTS.md`, `AGENT_WORKFLOW.md`, and the selected task. Create a worksheet before changing code.
2. Work in small verified slices. Start the app and exercise changed paths. Write targeted tests and update the test catalog and affected system docs as you go.
3. Run research, plan, implementation, and wrap-up review stages through `bin/agent-review`. Prefer an independent provider when configured; record unavailable review capability plainly.
4. Before stopping, run `bin/agent-validate full`, visual/benchmark checks when applicable, and `bin/agent-sweep`. Fix actionable failures within the task scope.
5. Complete the worksheet, append feedback, update `TODOS.md`, and commit all related artifacts together. Add tag `worksheet/<name>` only after verifying it is available.

If blocked by missing authority, credentials, a non-ready task, or an external dependency, document exact evidence and the narrowest next action in the worksheet and queue. Do not guess or retry destructive actions.
