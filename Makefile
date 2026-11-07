# Common tasks. Python uses uv; the frontend uses npm.
.PHONY: install test lint format typecheck gate run frontend-install frontend-test frontend-dev e2e clean help

install:
	uv sync
	cd frontend && npm ci

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff format .

typecheck:
	uv run mypy

gate:            # format, lint, type-check, test; real exit status
	tools/gate.sh

run:             # screening API on http://127.0.0.1:8000
	uv run rh serve

frontend-install:
	cd frontend && npm ci

frontend-test:
	cd frontend && npm run typecheck && npm test

frontend-dev:    # web app on http://localhost:3000 (start `make run` first)
	cd frontend && NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev

e2e:             # Playwright; both servers must be running
	cd frontend && npx playwright test

clean:
	find . -type d \( -name __pycache__ -o -name .mypy_cache -o -name .ruff_cache -o -name .pytest_cache \) -prune -exec rm -rf {} +
	rm -rf dist build htmlcov .coverage

help:
	@grep -E '^[a-z-]+:' Makefile | sed 's/:.*#/  -/; s/:$$//'
