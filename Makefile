.PHONY: install dev test lint typecheck check setup uninstall update doctor help

# ============================================
# Installation
# ============================================

install: ## Install proofloop globally
	@command -v uv >/dev/null 2>&1 || { echo "Installing uv..."; curl -LsSf https://astral.sh/uv/install.sh | sh; }
	uv tool install . --editable --force
	@echo ""
	@echo "Installed! Run 'proofloop --help' to verify."
	@echo "If not found, run: uv tool update-shell && restart your terminal"

setup: install ## Alias for install

uninstall: ## Remove proofloop
	uv tool uninstall proofloop 2>/dev/null || echo "proofloop is not installed"
	@echo "Uninstalled."

update: ## Update from git and reinstall
	git pull
	uv tool install . --editable --force
	@echo "Updated."

# ============================================
# Development
# ============================================

dev: ## Install dev dependencies
	uv sync --all-extras
	uv run pre-commit install
	@echo "Dev environment ready."

dev-server: ## Run development web server
	uv run uvicorn src.web.factory:create_app --factory --reload --host 0.0.0.0 --port 8000

# ============================================
# Testing & Quality
# ============================================

test: ## Run tests
	LOGURU_LEVEL=DEBUG uv run pytest tests/ -v -s --tb=short

test-cov: ## Run tests with coverage (90% required)
	LOGURU_LEVEL=DEBUG uv run pytest tests/ -v --tb=short --cov=src --cov-report=term-missing --cov-fail-under=90

lint: ## Run linter
	uv run ruff check src tests

format: ## Format code
	uv run ruff format src tests
	uv run ruff check --fix src tests

typecheck: ## Run type checker
	uv run mypy src

pre-commit: ## Run all pre-commit hooks
	uv run pre-commit run --all-files

check: lint typecheck test ## Run all checks (lint, typecheck, test)

# ============================================
# Database (optional)
# ============================================

migrate: ## Run database migrations
	uv run alembic upgrade head

migrate-new: ## Create new migration
	@read -p "Migration message: " msg; \
	uv run alembic revision --autogenerate -m "$$msg"

# ============================================
# Docker (optional)
# ============================================

docker-up: ## Start docker services
	docker compose up -d

docker-down: ## Stop docker services
	docker compose down

# ============================================
# Utilities
# ============================================

doctor: ## Check development environment
	@echo "Checking environment..."
	@echo ""
	@echo "Python:" && python3 --version
	@echo ""
	@echo "uv:" && (uv --version 2>/dev/null || echo "not installed")
	@echo ""
	@echo "proofloop:" && (proofloop --version 2>/dev/null || echo "not installed")
	@echo ""
	@echo "git:" && git --version
	@echo ""
	@echo "Environment check complete."

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
