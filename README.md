# Axmed Document Intelligence

This repository contains the Axmed quotation-intelligence application and its agent operating system.

## Start locally

Requires Python 3.12+ with [uv](https://docs.astral.sh/uv/) and Node.js 22+ with npm.

```bash
uv sync --project backend --all-groups
npm --prefix frontend install
make dev
```

The API is available at `http://127.0.0.1:8000` and the review desk at `http://127.0.0.1:5173`. Local SQLite data and uploaded sources are created under `data/` and are intentionally untracked.

## Validate

```bash
make lint
make test
make build
```

`docs/plans/implementation-plan.md` is the delivery sequence, and `AGENTS.md` routes implementation work to the relevant system documentation and checks.
