.PHONY: dev test lint db-clean celery docker-up install setup prod load-test metrics-up metrics-down view-metrics view-grafana health-check view-prometheus view-grafana-dashboards

# ── Quick Start ────────────────────────────────────────────────
# One command to start everything (single terminal)
dev:
	@echo "Starting AetherDesk..."
	@echo "  API:   http://localhost:8000"
	@echo "  UI:    http://127.0.0.1:3001"
	@echo "  Docs:  http://localhost:8000/docs"
	@echo ""
	python -c "import subprocess, sys, time, os; \
		api = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'src.api.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000'], cwd=r'$(CURDIR)'); \
		time.sleep(2); \
		ui = subprocess.Popen(['npm', 'run', 'dev'], cwd=r'$(CURDIR)/agent-ui', shell=True); \
		print('\nPress Ctrl+C to stop all services\n'); \
		try: \
			api.wait(); \
		except KeyboardInterrupt: \
			pass; \
		finally: \
			api.terminate(); ui.terminate()"

# One-time setup: generate keys, init DB, create .env
setup:
	@echo "=== AetherDesk Setup ==="
	@if not exist .env (copy .env.example .env >nul && echo ".env created from template") else (echo ".env already exists, skipping")
	@python -c "from cryptography.fernet import Fernet; open('.env','a').write(f'\nENCRYPTION_KEY={Fernet.generate_key().decode()}\n') if 'REPLACE_ME_WITH_A_STRONG_FERNET_KEY' in open('.env').read() else None"
	@python -c "import secrets; open('.env','a').write(f'\nJWT_SECRET={secrets.token_urlsafe(32)}\n') if 'REPLACE_ME_WITH_A_STRONG_JWT_SECRET' in open('.env').read() else None"
	@python -c "import secrets; open('.env','a').write(f'\nINTERNAL_API_KEY={secrets.token_urlsafe(32)}\n') if 'REPLACE_ME_WITH_A_STRONG_INTERNAL_KEY' in open('.env').read() else None"
	@echo "Keys generated. Edit .env to add Twilio/Groq/Deepgram credentials."
	@echo "Run 'make dev' to start."

# Production: docker compose up
prod:
	docker compose up --build -d
	@echo "AetherDesk running at http://localhost:3000"

# ── Install ────────────────────────────────────────────────────
install:
	pip install -r requirements.txt
	pip install pre-commit
	pre-commit install
	cd agent-ui && npm install

# ── Testing ────────────────────────────────────────────────────
test:
	USE_POSTGRES=false python -m pytest tests/test_db_refactor.py tests/test_health.py -v --tb=short

test-all:
	USE_POSTGRES=false python -m pytest tests/ -v --tb=short

test-cov:
	USE_POSTGRES=false python -m pytest tests/ --cov=src --cov-report=term-missing --cov-report=html

# ── Linting ────────────────────────────────────────────────────
lint:
	python -m ruff check src/

lint-fix:
	python -m ruff check src/ --fix

format:
	python -m ruff format src/

# ── Database ───────────────────────────────────────────────────
db-clean:
	rm -f aetherdesk.db chroma_db/ -rf
	echo "SQLite + chroma_db cleaned"

db-init:
	USE_POSTGRES=false python -c "from src.api.services.database import init_sqlite_schema; init_sqlite_schema(); print('Schema created')"

# ── Services ───────────────────────────────────────────────────
celery:
	celery -A src.api.services.celery_app worker --loglevel=info --concurrency=4

celery-beat:
	celery -A src.api.services.celery_app beat --loglevel=info

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# ── Load Testing ───────────────────────────────────────────────
load-test:
	k6 run tests/load/k6_call_flow.js --env API_URL=http://localhost:8000

load-test-concurrent:
	k6 run tests/load/k6_concurrent_calls.js --env API_URL=http://localhost:8000

# ── Security ───────────────────────────────────────────────────
secrets-scan:
	detect-secrets scan --baseline .secrets.baseline

secrets-audit:
	detect-secrets audit .secrets.baseline

# ── Monitoring & Observability ─────────────────────────────────
metrics-up:
	docker compose up -d prometheus grafana
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3003 (admin/aetherdesk)"

metrics-down:
	docker compose stop prometheus grafana

view-metrics:
	@echo "Opening Prometheus..."
	start http://localhost:9090

view-grafana:
	@echo "Opening Grafana..."
	start http://localhost:3003

health-check:
	@echo "=== API Health ==="
	@curl -s http://localhost:8000/health | python -m json.tool
	@echo "=== Readiness ==="
	@curl -s http://localhost:8000/health/ready | python -m json.tool
	@echo "=== SLA ==="
	@curl -s http://localhost:8000/health/sla | python -m json.tool
	@echo "=== Vendors ==="
	@curl -s http://localhost:8000/health/vendors | python -m json.tool

view-prometheus:
	@echo "Opening Prometheus UI..."
	start http://localhost:9090/targets

view-grafana-dashboards:
	@echo "Opening Grafana dashboards..."
	start http://localhost:3003/d/aetherdesk/overview
