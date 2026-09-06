.DEFAULT_GOAL := help

.PHONY: help dev test lint build eval

help:
	@echo "make dev    Start FastAPI and Vue together"
	@echo "make test   Run backend and frontend tests"
	@echo "make lint   Run backend and frontend linters"
	@echo "make build  Build the frontend"
	@echo "make eval   Run the stored recorded evaluation"

dev:
	@bin/dev

test:
	@PYTHONPATH=backend uv run --project backend pytest backend/tests -q
	@npm --prefix frontend test

lint:
	@PYTHONPATH=backend uv run --project backend ruff check backend
	@npm --prefix frontend run lint

build:
	@npm --prefix frontend run build

eval:
	@backend/bin/run-evals
