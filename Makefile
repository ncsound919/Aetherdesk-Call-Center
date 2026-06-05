# AetherDesk Call Center — Project Makefile
# Replaces the ad-hoc launcher/debug scripts that have been removed.
# Run `make help` to see all available commands.

.DEFAULT_GOAL := help

# ── Environment ──────────────────────────────────────────────────────────────
.PHONY: install install-dev
install:       ## Install production dependencies
	pip install -e .

install-dev:   ## Install all dev + ML dependencies
	pip install -e ".[dev,ml]"
	pre-commit install

# ── Development server ───────────────────────────────────────────────────────
.PHONY: dev api ui
dev:           ## Start API + UI in development mode (requires Docker)
	docker compose up --build

api:           ## Start API server only (hot-reload)
	uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

ui:            ## Start React UI dev server
	cd agent-ui && npm run dev

# ── Database ──────────────────────────────────────────────────────────────────
.PHONY: db-migrate db-upgrade db-reset
db-migrate:    ## Create a new Alembic migration (MSG required: make db-migrate MSG="your message")
	alembic revision --autogenerate -m "$(MSG)"

db-upgrade:    ## Apply all pending Alembic migrations
	alembic upgrade head

db-reset:      ## ⚠️  Drop and recreate schema (dev/staging only)
	@echo "WARNING: This will destroy all data. Press Ctrl-C to abort."
	@sleep 5
	alembic downgrade base && alembic upgrade head

# ── Testing ───────────────────────────────────────────────────────────────────
.PHONY: test test-unit test-e2e test-load
test:          ## Run all unit + integration tests
	pytest tests/ -v

test-unit:     ## Run only unit tests (fast, no external services)
	pytest tests/unit/ -v -m "not e2e_core and not e2e_ml"

test-e2e:      ## Run core E2E tests (deterministic, no ML deps)
	pytest tests/ -v -m e2e_core

test-load:     ## Run load tests with Locust (requires running server)
	locust -f tests/load/locustfile.py --headless -u 50 -r 5 --run-time 60s

# ── Code Quality ─────────────────────────────────────────────────────────────
.PHONY: lint format typecheck
lint:          ## Run ruff linter
	ruff check apps/ tests/

format:        ## Auto-format with black + ruff
	black apps/ tests/
	ruff check --fix apps/ tests/

typecheck:     ## Run mypy static type checking
	mypy apps/

# ── Docker / K8s ──────────────────────────────────────────────────────────────
.PHONY: docker-build k8s-apply k8s-secrets
docker-build:  ## Build all Docker images
	docker compose build

k8s-apply:     ## Apply Kubernetes manifests (KUBECONFIG must be set)
	kubectl apply -f kubernetes/

k8s-secrets:   ## Seal secrets with kubeseal (requires kubeseal + cert)
	@echo "See kubernetes/README.md for secret sealing instructions."

# ── Utilities ─────────────────────────────────────────────────────────────────
.PHONY: clean help
clean:         ## Remove build artifacts, caches, and coverage reports
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ .coverage htmlcov/ .mypy_cache/

help:          ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
