.PHONY: dev migrate makemigrations test install sync lint format audit upgrade

# Development server
dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8090

# Run migrations
migrate:
	uv run alembic upgrade head

# Create new migration (usage: make makemigrations m="migration message")
makemigrations:
	uv run alembic revision --autogenerate -m "$(m)"

# Run tests
test:
	uv run pytest

# Install dependencies (incluye grupo dev: ruff, pytest)
install:
	uv sync

# Sync dependencies (same as install)
sync:
	uv sync

# Lint (ruff check + format check)
lint:
	uv run ruff check app scripts alembic/env.py
	uv run ruff format --check app scripts alembic/env.py

# Auto-fix lint and format
format:
	uv run ruff check --fix app scripts alembic/env.py
	uv run ruff format app scripts alembic/env.py

# Security audit of uv.lock against PyPI/OSV advisories
audit:
	uvx uv-secure

# Upgrade all dependencies within pyproject constraints, then re-audit
upgrade:
	uv lock --upgrade
	uv sync
	$(MAKE) audit
