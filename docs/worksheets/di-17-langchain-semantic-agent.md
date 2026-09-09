# Worksheet: di-17-langchain-semantic-agent

> Purpose: implement a bounded LangChain semantic-extraction agent across JSON, PDF, email, OCR-assisted, and direct-vision sources.
> Create this file before meaningful implementation and keep it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> The user requested that this session remain uncommitted.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

- Preserve current deterministic preparation and media routing.
- Replace fixed semantic calls with a shared LangChain `create_agent` loop.
- Require the agent to submit at least one complete candidate to deterministic validation.
- Continue investigation while validation feedback changes, within model/tool budgets.
- Remove the separate PDF narrative-enrichment and JSON completeness-audit behavior from active processing.
- Keep email reconciliation, image peer results, commercial rules, confidence, persistence, and human review deterministic.
- Document explicit LangGraph orchestration as a future option, not the active implementation.

## Context and constraints

- Earlier interrupted work left an incomplete LangGraph implementation in the worktree. It was removed before the LangChain implementation proceeded.
- Existing uncommitted documentation changes belong to this semantic-extraction design thread and must be preserved.
- The public test seams are the shared semantic-agent runner and existing document processing APIs.
- Do not commit automatically.

## Plan

1. Add public agent-loop tests and a provider-independent runner seam.
2. Implement the LangChain agent with deterministic validation and progress detection.
3. Route each source processor through the shared agent.
4. Remove active PDF enrichment and JSON audit duplication.
5. Update evaluations, system docs, test catalog, worksheet, and feedback.
6. Run targeted/full validation, the application, staged reviews, and a sweep.

## Work log and evidence

- 2026-09-09: Removed the partial explicit LangGraph runner, direct dependency declaration, narrative-completion code, tests, and worksheet left by the interrupted attempt.
- 2026-09-09: Added the LangChain agent contract, deterministic validation tool, repeated-issue detection, structured response, and model/tool call limits.
- 2026-09-09: Routed JSON, PDF, email, OCR-assisted, direct-vision, and live evaluation paths through the shared agent seam.
- 2026-09-09: Moved production JSON semantic execution behind durable upload persistence and the API background-task boundary; disabled-background test mode remains synchronous by configuration.
- 2026-09-09: Removed the active PDF narrative call and JSON completeness-audit call. LangGraph remains only a documented future state-management option; its direct dependency and runner code are absent.
- 2026-09-09: Flattened the agent runner to `run_semantic_investigation`; removed the duplicate final-response model, constructor-only agent class, nested JSON inspector, and separate execution/validation tracker classes. One private per-run state record now owns the mutable investigation facts.

## Tests, app run, and validation

- Focused agent and processor suites: 27 passed.
- Final backend validation: Ruff passed, mypy passed for 28 source files, and 102 pytest tests passed with one third-party Starlette deprecation warning.
- Structural-refactor check: Ruff and mypy passed for the changed agent/provider modules; `tests/test_semantic_agent.py` and `tests/test_langchain_gemini.py` passed (21 tests, one pre-existing third-party Starlette deprecation warning).
- Targeted validation: `bin/agent-validate targeted` passed: frontend lint/component tests, backend Ruff, backend mypy, and 122 backend tests. Browser/Playwright checks remain intentionally out of scope at the user's direction.
- Live application: `API_PORT=8017 WEB_PORT=5197 bin/dev` started both servers and `GET /health` returned `{"status":"ok","service":"axmed-document-intelligence"}`. The temporary processes were then stopped.
- Live application: `API_PORT=8011 WEB_PORT=5181 bin/dev`; backend `/health` returned healthy. Frontend/browser validation is intentionally outside this backend-first stopping point at the user's direction.
- Implementation review dispatcher reported no independent provider configured; isolated quality/code/security review found one stale evaluation seam, which was routed through the agent and regression-tested.

## Review findings and resolutions

- The repository review dispatcher had no independent provider configured. The isolated pass removed the last unused fixed structured-output method, routed live evaluations through the agent, corrected telemetry naming, and confirmed that no explicit LangGraph runner/import remains.
- Structural-refactor review: no independent review provider was configured. Isolated quality review confirmed public behavior is protected by the direct-function and ordered-provider tests; code-quality review confirmed agent control flow is now visible in one function and one tool factory; security review confirmed log payloads and provider boundaries were unchanged. `git diff --check` passed.

## Docs updated

- README, write-up, PRD, architecture, testing strategy, test catalog, task queue, and this worksheet.

## Handoff / remaining work
