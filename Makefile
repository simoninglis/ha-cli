.PHONY: help install dev lint test coverage build clean run

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	poetry install --only main

dev: ## Install all dependencies including dev
	poetry install

lint: ## Run linting checks
	poetry run ruff check ha_cli/
	poetry run mypy ha_cli/

format: ## Format code
	poetry run ruff format ha_cli/
	poetry run ruff check --fix ha_cli/

test: ## Run tests
	poetry run pytest tests/ -v

coverage: ## Run tests with coverage
	poetry run pytest tests/ --cov=ha_cli --cov-report=html --cov-report=term

build: ## Build the package
	poetry build

clean: ## Clean build artifacts
	rm -rf dist/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run: ## Run the CLI tool
	poetry run ha-cli --help

# Development shortcuts
list: ## List automations (dev shortcut)
	poetry run ha-cli automations list

shell: ## Open Python shell with project context
	poetry run python
