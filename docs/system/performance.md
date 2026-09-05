# Performance

> Purpose: guard user-critical performance from accidental regressions.
> Status: establish representative scenarios and budgets once the application stack exists.
> Update when metrics, hardware/environment, scenarios, budgets, or profiling tools change.
> Owner persona: performance engineer.
> Related: agent review, testing, architecture.
> Search terms: benchmark, profile, latency, throughput, memory, budget.
> Compare like-for-like measurements and investigate material variance before claiming a change is faster.

## Policy

Benchmark user-critical paths with fixed inputs and recorded environment details. Keep a baseline and an allowed regression budget. Use targeted profiling to explain a regression before optimizing; do not replace a slower path solely because a microbenchmark changed.
