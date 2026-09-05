# Coding Conventions

> Purpose: repository-specific conventions that reviewers and automated checks enforce.
> Status: baseline; refine only when a convention is repeatedly valuable.
> Update with a lint rule where deterministic enforcement is feasible.
> Owner persona: code-quality maintainer.
> Related: `bin/agent-validate`, `docs/system/agent-review.md`.
> Search terms: conventions, style, lint, naming, errors, dependencies.
> General language-style choices follow the selected stack’s formatter unless specified here.

## Baseline

- Prefer clear names, small cohesive modules, explicit error handling, and tests at behavior seams.
- Do not introduce dependencies or configuration without documenting their reason and operational impact.
- Keep generated files out of hand-edited source unless the generator and regeneration command are documented.
- Add an auto-fixable formatter/linter as soon as the runtime is selected; put recurring review findings into it when practical.
