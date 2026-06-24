.PHONY: dev test lint db-clean celery docker-up install

# ── Development ────────────────────────────────────────────────
install:
	pip install -r requirements.txt
	pip install pre-commit
	pre-commit install

dev:
	uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

# ── Testing ─────────────────────────────────────────────────────
test:
	USE_POSTGRES=false python -m pytest tests/test_db_refactor.py tests/test_health.py -v --tb=short

test-all:
	USE_POSTGRES=false python -m pytest tests/ -v --tb=short

test-cov:
	USE_POSTGRES=false python -m pytest tests/ --cov=apps --cov-report=term-missing --cov-report=html

# ── Linting ─────────────────────────────────────────────────────
lint:
	python -m ruff check apps/

lint-fix:
	python -m ruff check apps/ --fix

format:
	python -m ruff format apps/

# ── Database ────────────────────────────────────────────────────
db-clean:
	rm -f aetherdesk.db chroma_db/ -rf
	echo "SQLite + chroma_db cleaned"

db-init:
	USE_POSTGRES=false python -c "from apps.api.services.database import init_sqlite_schema; init_sqlite_schema(); print('Schema created')"

# ── Services ────────────────────────────────────────────────────
celery:
	celery -A apps.api.services.celery_app worker --loglevel=info --concurrency=4

celery-beat:
	celery -A apps.api.services.celery_app beat --loglevel=info

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# ── Security ────────────────────────────────────────────────────
secrets-scan:
	detect-secrets scan --baseline .secrets.baseline

secrets-audit:
	detect-secrets audit .secrets.baseline
