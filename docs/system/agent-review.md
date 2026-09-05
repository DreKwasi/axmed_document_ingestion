# Agent Review Protocol

> Purpose: independent, staged review that catches issues before and after implementation.
> Run at research, plan, implementation, and wrap-up using `bin/agent-review <stage>`.
> Prefer a different model/provider for review; record when this is unavailable.
> Owner personas jointly maintain their assigned system docs and surface doc drift.
> Findings require severity, evidence, impact, and a concrete fix or accepted rationale.
> Search terms: review, persona, security, performance, maintainability, AI smell.
> Do not approve your own implementation merely by restating its intent.

## Personas and ownership

| Persona | Focus | Owns |
| --- | --- | --- |
| Systems maintainer | boundaries, dependencies, operability | architecture |
| Quality engineer | behavior, coverage, false confidence | testing, test catalog, false-confidence audits |
| Security/domain reviewer | auth, data exposure, domain invariants | relevant domain docs, threat notes |
| Performance engineer | critical paths, budgets, regressions | performance |
| UX/accessibility reviewer | user flow, states, visual quality | visual regression |
| Code-quality maintainer | readability, complexity, AI-generated smells | coding conventions |

## Stage prompts

- **Research:** challenge assumptions, locate relevant constraints/docs, and identify missing evidence.
- **Plan:** look for omitted cases, risky migrations, validation gaps, and unnecessarily broad changes.
- **Implementation:** inspect correctness, security, performance, maintainability, tests, and doc updates against actual diffs.
- **Wrap-up:** verify claims against commands/results, unresolved risk, artifact completeness, and handoff quality.

Use an isolated context for each persona when possible. A “no findings” result must say what was inspected.
