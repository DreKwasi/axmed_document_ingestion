# Agent Tooling and Hooks

> Purpose: configure reliable local automation without hiding unavailable capability.
> `bin/agent-lint --fix` is the pre-commit repair path; it must leave code lint-clean or fail.
> Configure an approved low-cost repair CLI in `AGENT_FIX_COMMAND` only for non-interactive mechanical fixes.
> Configure an independent reviewer wrapper in `AGENT_REVIEW_COMMAND`; it receives `AGENT_REVIEW_STAGE`.
> Run `bin/setup-hooks` once after Git initialization to enable the versioned pre-commit hook.
> Owner persona: code-quality maintainer.
> Search terms: tooling, hook, lint, fix, review command, validation.

## Design

The repository hook is intentionally short: it runs deterministic auto-fix then requires a clean lint result. A configured repair command is an opt-in fallback when deterministic tooling cannot repair an issue. The fallback must be non-interactive, restricted to the current repository, and followed by a fresh lint pass. It must never be used to conceal test or security failures.

## Adding a helper

Put portable helpers in `bin/`, document them in `tools/README.md`, expose `--help` when inputs are non-obvious, use strict shell mode, state external requirements, and test the happy/failure path. Add stack-aware behavior only after the stack is committed to `architecture.md`.
