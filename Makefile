# Makefile for TouchTerrain Project
# Supports both uv and standard Python tooling

.PHONY: help install install-dev test test-verbose test-coverage lint format clean build docs serve-docs pre-commit-install pre-commit-run all check

# Detect if uv is available
UV := $(shell command -v uv 2> /dev/null)
PYTHON := $(if $(UV),uv run python,python)
PIP := $(if $(UV),uv pip,pip)
PYTEST := $(if $(UV),uv run pytest,pytest)
PRE_COMMIT := $(if $(UV),uv run pre-commit,pre-commit)

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# Default target
.DEFAULT_GOAL := help

## help: Display this help message
help:
	@echo "$(BLUE)TouchTerrain Project - Available Make Targets$(NC)"
	@echo ""
	@echo "$(GREEN)Setup:$(NC)"
	@echo "  make install          - Install package and dependencies"
	@echo "  make install-dev      - Install package with development dependencies"
	@echo "  make pre-commit-install - Install pre-commit hooks"
	@echo ""
	@echo "$(GREEN)Development:$(NC)"
	@echo "  make format           - Format code with black and isort"
	@echo "  make lint             - Run linters (ruff)"
	@echo "  make pre-commit-run   - Run all pre-commit hooks"
	@echo "  make check            - Run format, lint, and tests"
	@echo ""
	@echo "$(GREEN)Testing:$(NC)"
	@echo "  make test             - Run fast tests (excludes slow/EE tests)"
	@echo "  make test-verbose     - Run fast tests with verbose output"
	@echo "  make test-all         - Run ALL tests including slow/EE tests"
	@echo "  make test-ee          - Run only Earth Engine tests (requires auth)"
	@echo "  make test-coverage    - Run tests with coverage report"
	@echo "  make test-watch       - Run tests in watch mode (requires pytest-watch)"
	@echo ""
	@echo "$(GREEN)Build & Package:$(NC)"
	@echo "  make build            - Build distribution packages"
	@echo "  make clean            - Remove build artifacts and caches"
	@echo "  make clean-all        - Remove all artifacts including venv"
	@echo ""
	@echo "$(GREEN)Documentation:$(NC)"
	@echo "  make docs             - Build documentation (if available)"
	@echo "  make serve-docs       - Serve documentation locally"
	@echo ""
	@echo "$(GREEN)Utility:$(NC)"
	@echo "  make all              - Install, format, lint, and test"
	@echo "  make env-info         - Show environment information"
	@echo ""
ifdef UV
	@echo "$(GREEN)✓ Using uv for faster operations$(NC)"
else
	@echo "$(YELLOW)⚠ uv not found, falling back to standard Python tools$(NC)"
	@echo "$(YELLOW)  Install uv for faster operations: curl -LsSf https://astral.sh/uv/install.sh | sh$(NC)"
endif

## env-info: Display environment information
env-info:
	@echo "$(BLUE)Environment Information:$(NC)"
	@echo "Python: $(shell $(PYTHON) --version 2>&1)"
	@echo "pip: $(shell $(PIP) --version 2>&1 | head -1)"
ifdef UV
	@echo "uv: $(shell uv --version)"
	@echo "Status: $(GREEN)Using uv$(NC)"
else
	@echo "uv: $(YELLOW)not installed$(NC)"
	@echo "Status: $(YELLOW)Using standard Python tools$(NC)"
endif
	@echo "pytest: $(shell $(PYTEST) --version 2>&1 | head -1 || echo 'not installed')"
	@echo "Working directory: $(shell pwd)"

## install: Install package and dependencies
install:
	@echo "$(BLUE)Installing TouchTerrain...$(NC)"
ifdef UV
	uv pip install -e .
else
	pip install -e .
endif
	@echo "$(GREEN)✓ Installation complete$(NC)"

## install-dev: Install package with development dependencies
install-dev:
	@echo "$(BLUE)Installing TouchTerrain with development dependencies...$(NC)"
ifdef UV
	uv pip install -e ".[dev]"
	uv pip install pytest pytest-cov pytest-mock pre-commit black isort ruff
else
	pip install -e ".[dev]"
	pip install pytest pytest-cov pytest-mock pre-commit black isort ruff
endif
	@echo "$(GREEN)✓ Development installation complete$(NC)"

## pre-commit-install: Install pre-commit hooks
pre-commit-install:
	@echo "$(BLUE)Installing pre-commit hooks...$(NC)"
	$(PRE_COMMIT) install
	@echo "$(GREEN)✓ Pre-commit hooks installed$(NC)"

## pre-commit-run: Run all pre-commit hooks
pre-commit-run:
	@echo "$(BLUE)Running pre-commit hooks...$(NC)"
	$(PRE_COMMIT) run --all-files

## format: Format code with black and isort
format:
	@echo "$(BLUE)Formatting code...$(NC)"
ifdef UV
	uv run isort .
	uv run black .
else
	isort .
	black .
endif
	@echo "$(GREEN)✓ Code formatted$(NC)"

## lint: Run linters
lint:
	@echo "$(BLUE)Running linters...$(NC)"
ifdef UV
	uv run ruff check .
else
	ruff check .
endif

## test: Run tests (excludes slow/Earth Engine tests)
test:
	@echo "$(BLUE)Running tests...$(NC)"
	$(PYTEST) -q -m "not earth_engine and not slow"

## test-verbose: Run tests with verbose output
test-verbose:
	@echo "$(BLUE)Running tests (verbose)...$(NC)"
	$(PYTEST) -v -m "not earth_engine and not slow"

## test-all: Run ALL tests including slow/Earth Engine tests
test-all:
	@echo "$(BLUE)Running all tests (including slow/EE tests)...$(NC)"
	@echo "$(YELLOW)Note: Earth Engine tests require authentication$(NC)"
	$(PYTEST) -v

## test-coverage: Run tests with coverage report (excludes slow/EE tests)
test-coverage:
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	$(PYTEST) -m "not earth_engine and not slow" --cov=touchterrain --cov-report=html --cov-report=term-missing
	@echo "$(GREEN)✓ Coverage report generated in htmlcov/index.html$(NC)"

## test-ee: Run Earth Engine tests (requires authentication)
test-ee:
	@echo "$(BLUE)Running Earth Engine tests...$(NC)"
	@echo "$(YELLOW)Note: These tests require Earth Engine authentication$(NC)"
	$(PYTEST) -v -m "earth_engine"

## test-watch: Run tests in watch mode (requires pytest-watch)
test-watch:
	@echo "$(BLUE)Running tests in watch mode...$(NC)"
ifdef UV
	uv run ptw
else
	ptw
endif

## build: Build distribution packages
build: clean
	@echo "$(BLUE)Building distribution packages...$(NC)"
ifdef UV
	uv build
else
	$(PYTHON) -m build
endif
	@echo "$(GREEN)✓ Build complete - check dist/ directory$(NC)"

## clean: Remove build artifacts and caches
clean:
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.orig" -delete
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

## clean-all: Remove all artifacts including virtual environment
clean-all: clean
	@echo "$(YELLOW)Removing virtual environment...$(NC)"
	rm -rf .venv/
	rm -rf venv/
	@echo "$(GREEN)✓ Full cleanup complete$(NC)"

## docs: Build documentation
docs:
	@echo "$(BLUE)Building documentation...$(NC)"
	@if [ -d "docs" ]; then \
		cd docs && make html; \
		echo "$(GREEN)✓ Documentation built$(NC)"; \
	else \
		echo "$(YELLOW)No docs directory found$(NC)"; \
	fi

## serve-docs: Serve documentation locally
serve-docs:
	@echo "$(BLUE)Serving documentation at http://localhost:8000$(NC)"
	@if [ -d "docs/_build/html" ]; then \
		cd docs/_build/html && $(PYTHON) -m http.server 8000; \
	else \
		echo "$(YELLOW)Documentation not built. Run 'make docs' first.$(NC)"; \
	fi

## check: Run all checks (format, lint, test)
check: format lint test
	@echo "$(GREEN)✓ All checks passed!$(NC)"

## all: Complete setup - install dev dependencies, install hooks, and run checks
all: install-dev pre-commit-install check
	@echo "$(GREEN)✓ Complete setup finished!$(NC)"

# Advanced test targets

## test-unit: Run only unit tests
test-unit:
	@echo "$(BLUE)Running unit tests...$(NC)"
	$(PYTEST) -v -m "not integration"

## test-integration: Run only integration tests
test-integration:
	@echo "$(BLUE)Running integration tests...$(NC)"
	$(PYTEST) -v -m integration

## test-failed: Re-run only failed tests
test-failed:
	@echo "$(BLUE)Re-running failed tests...$(NC)"
	$(PYTEST) --lf -v

## test-parallel: Run tests in parallel (requires pytest-xdist)
test-parallel:
	@echo "$(BLUE)Running tests in parallel...$(NC)"
	$(PYTEST) -n auto

## test-debug: Run tests with debugging enabled
test-debug:
	@echo "$(BLUE)Running tests with debugger...$(NC)"
	$(PYTEST) -vv --pdb

# Git helpers

## git-status: Show git status
git-status:
	@git status

## git-diff: Show unstaged changes
git-diff:
	@git diff

## git-staged: Show staged changes
git-staged:
	@git diff --staged

# Maintenance targets

## update-deps: Update all dependencies
update-deps:
	@echo "$(BLUE)Updating dependencies...$(NC)"
ifdef UV
	uv pip install --upgrade -e ".[dev]"
else
	pip install --upgrade -e ".[dev]"
endif
	@echo "$(GREEN)✓ Dependencies updated$(NC)"

## security-check: Run security checks (requires safety)
security-check:
	@echo "$(BLUE)Running security checks...$(NC)"
ifdef UV
	uv run safety check
else
	safety check
endif
