# Standard Agent Workflow

> Purpose: the default implementation loop for this repository.
> Use this for features, fixes, refactors, and autonomous work unless a narrower task says otherwise.
> Always run the application and exercise changed behavior; automated checks complement, not replace, this.
> Keep tests, test inventory, worksheets, feedback, and affected system docs in the same change set.
> Use targeted validation during work and full validation at handoff.
> Prefer small reversible increments with concrete evidence over broad unverified edits.

## The loop

1. **Orient.** Read `AGENTS.md`, the task, `TODOS.md`, and relevant system-doc summaries. Create a worksheet from `docs/worksheets/TEMPLATE.md` before meaningful work.
2. **Research.** Inspect the real code and current behavior. Run the app early. Record evidence, constraints, and unknowns in the worksheet. Run an independent or persona-based research review.
3. **Plan.** State the smallest viable change, acceptance checks, docs to update, and risks. Run a plan review before broad implementation.
4. **Implement and verify in loops.** Add or update focused tests, change one coherent slice, run `bin/agent-validate targeted`, then run the app and exercise the exact path. Fix problems immediately.
5. **Harden.** Update system docs and the test catalog. Add a visual baseline for UI changes and a benchmark for performance-sensitive changes. Run implementation review personas.
6. **Wrap up.** Run `bin/agent-validate full`, required sweeps/audits, the app, and wrap-up review. Record commands/results and remaining risks in the worksheet and feedback log.
7. **Commit and tag.** When Git exists, commit code, tests, docs, worksheet, and feedback together. Tag the final commit `worksheet/<worksheet-name>` after confirming the tag is unused.

## Non-negotiable evidence

- “Tested” names the command and outcome, or the exact manual path exercised.
- A test must observe externally meaningful behavior. Avoid tests that only assert mocked implementation details.
- A passing linter is not proof the app starts. A passing screenshot diff is not proof interactions work.
- If a check cannot run, say why, create/queue the enabling work in `TODOS.md`, and do not describe the validation as passed.

## Review stages

Run `bin/agent-review research|plan|implementation|wrap-up`. Separate model/provider review is preferred when accessible. If it is not, perform isolated passes using the personas and checklists in `docs/system/agent-review.md`; do not reuse the same unstructured reasoning pass as its own review.
