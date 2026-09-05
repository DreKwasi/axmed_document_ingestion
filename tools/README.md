# Agent Tooling

> Purpose: small, portable helpers that make repeatable agent work reliable.
> Add a script when it removes recurring manual steps or makes validation deterministic.
> Scripts should be composable, non-interactive by default, documented with `--help`, and safe on a clean checkout.
> Prefer clear exit codes and actionable messages over clever hidden behavior.
> Test each script after changing it and document any external command/environment variable it needs.
> Keep stack-specific logic in scripts rather than copying it into agent prompts.

`bin/agent-validate` dispatches available checks. `bin/agent-review` dispatches configured independent reviews or records a local persona checklist. `bin/agent-sweep` scans recent work for required artifacts. `bin/false-confidence-audit` guides and records focused test-strength audits.
