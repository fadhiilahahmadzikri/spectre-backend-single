SHELL := powershell.exe
.SHELLFLAGS := -NoProfile -Command

.PHONY: help install dev dev-win test-poc worker lint format typecheck check test test-unit test-integration test-cov test-newman test-newman-report test-all migrate migrate-new migrate-down seed seed-force seed-reset seed-list docker-up docker-down docker-build docker-logs docs docs-redoc openapi-export health env-check bootstrap reset ci clean clean-pyc

help: ## Show available commands
	@Get-Content $(MAKEFILE_LIST) | Select-String '^[a-zA-Z_-]+:.*##' | ForEach-Object { $$_ -replace ':.*## ', '`t' } | Sort-Object

# ==============================================================================
# Development
# ==============================================================================

install: ## Install all dependencies (production + dev)
	uv sync --all-extras

dev: ## Run development server (Unix)
	$$env:PYTHONDONTWRITEBYTECODE='1'; uv run uvicorn spectre.main:create_app --factory --host 0.0.0.0 --port 8000 --reload

dev-win: clean-pyc ## Run development server (Windows, auto-clears cache)
	$$env:PYTHONDONTWRITEBYTECODE='1'; .venv\Scripts\python -m uvicorn "src.spectre.main:create_app" --factory --host 0.0.0.0 --port 8000 --reload

test-poc: ## Serve POC HTML UI client
	@echo "========================================================"
	@echo " UI Client ready at : http://localhost:8001/ "
	@echo " Network Access     : http://$$(ipconfig | Select-String 'IPv4' | ForEach-Object {$$_.Line.Split(':')[-1].Trim()} | Select-Object -First 1):8001/ "
	@echo "========================================================"
	.venv\Scripts\python -m http.server 8001 -d poc

worker: ## Run Celery worker
	uv run celery -A spectre.workers.celery_app worker --loglevel=info --concurrency=2

# ==============================================================================
# Quality
# ==============================================================================

lint: ## Run linter
	uv run ruff check src/ tests/

format: ## Format code
	uv run ruff format src/ tests/

typecheck: ## Run type checker
	uv run mypy src/spectre

check: lint typecheck ## Run all static checks (lint + types)

# ==============================================================================
# Testing
# ==============================================================================

test: ## Run all pytest tests
	uv run pytest

test-unit: ## Run unit tests only
	uv run pytest tests/unit -v

test-integration: ## Run integration tests only
	uv run pytest tests/integration -v

test-cov: ## Run tests with coverage report
	uv run pytest --cov=spectre --cov-report=html --cov-report=term-missing

test-newman: ## Run Newman API tests against local server
	newman run tests/postman/spectre-api-v1.postman_collection.json -e tests/postman/env-local.json --reporters cli

test-newman-hf: ## Run Newman API tests against Hugging Face Spaces
	newman run tests/postman/spectre-api-v1.postman_collection.json -e tests/postman/env-hf-spaces.json --reporters cli --timeout-request 30000

test-newman-report: ## Run Newman with HTML report (local)
	New-Item -ItemType Directory -Force -Path reports | Out-Null
	newman run tests/postman/spectre-api-v1.postman_collection.json -e tests/postman/env-local.json --reporters cli,htmlextra --reporter-htmlextra-export reports/api-report.html
	@echo "Report saved: reports/api-report.html"

test-newman-hf-report: ## Run Newman with HTML report (HF Spaces)
	New-Item -ItemType Directory -Force -Path reports | Out-Null
	newman run tests/postman/spectre-api-v1.postman_collection.json -e tests/postman/env-hf-spaces.json --reporters cli,htmlextra --reporter-htmlextra-export reports/api-report-hf.html --timeout-request 30000
	@echo "Report saved: reports/api-report-hf.html"

postman-push: ## Push collection to Postman cloud (syncs local → remote)
	uv run python scripts/postman_push.py

test-all: test test-newman ## Run full local test suite (pytest + Newman)

# ==============================================================================
# Database
# ==============================================================================

migrate: ## Run database migrations to latest (local)
	uv run alembic upgrade head

migrate-supabase: ## Run database migrations against Supabase (production)
	$$env:DATABASE_URL = (Select-String -Path .env.spaces -Pattern '^DATABASE_URL=(.+)$$' | ForEach-Object { $$_.Matches.Groups[1].Value }); uv run alembic upgrade head

migrate-new: ## Create new migration (usage: make migrate-new MSG="description")
	uv run alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback one migration
	uv run alembic downgrade -1

# ==============================================================================
# Seeders
# ==============================================================================

seed: ## Run all database seeders
	uv run python -m seeds all

seed-force: ## Force re-run all seeders (ignore idempotency)
	uv run python -m seeds all --force

seed-reset: ## Clear seed registry so seeders can re-run
	uv run python -m seeds reset --yes

seed-list: ## List all registered seeders with status
	uv run python -m seeds list

# ==============================================================================
# Docker / Infrastructure
# ==============================================================================

docker-up: ## Start infra services only (PostgreSQL, Redis)
	docker-compose up -d

docker-down: ## Stop all services
	docker-compose down

docker-build: ## Build Docker images
	docker-compose build

docker-logs: ## Tail service logs
	docker-compose logs -f

docker-dev: ## Start FULL containerized dev stack (zero local deps)
	docker compose -f docker-compose.dev.yml up --build

docker-dev-d: ## Start full dev stack (detached)
	docker compose -f docker-compose.dev.yml up --build -d

docker-dev-down: ## Stop full dev stack
	docker compose -f docker-compose.dev.yml down

docker-dev-logs: ## Tail full dev stack logs
	docker compose -f docker-compose.dev.yml logs -f

docker-test: ## Run Newman API tests inside Docker (full stack must be running)
	docker compose -f docker-compose.dev.yml --profile test run --rm newman

docker-reset: ## Full Docker reset (remove volumes, rebuild)
	docker compose -f docker-compose.dev.yml down -v
	docker compose -f docker-compose.dev.yml up --build -d
	@echo "Full reset complete. API at http://localhost:8000/docs"

# ==============================================================================
# Documentation & OpenAPI
# ==============================================================================

docs: ## Open Swagger UI in browser (local server must be running)
	Start-Process "http://localhost:8000/docs"

docs-redoc: ## Open ReDoc documentation in browser (local)
	Start-Process "http://localhost:8000/redoc"

docs-hf: ## Open Swagger UI on Hugging Face Spaces deployment
	Start-Process "https://thewhitenigs-spectre-backend.hf.space/docs"

docs-hf-redoc: ## Open ReDoc on Hugging Face Spaces
	Start-Process "https://thewhitenigs-spectre-backend.hf.space/redoc"

openapi-export: ## Export live OpenAPI schema to Docs/openapi.json
	$(PYPATH) uv run python -c "import json; from spectre.config import Settings; from spectre.main import create_app; app = create_app(settings=Settings(app_env='development', debug=True, database_url='sqlite+aiosqlite:///', redis_url='redis://localhost:6379/15', jwt_secret_key='x'*64, encryption_key='dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleTE=', model_path='artifact/best_model.keras')); open('Docs/openapi.json','w').write(json.dumps(app.openapi(), indent=2, default=str))"
	@echo "Exported: Docs/openapi.json"

# ==============================================================================
# Health & Environment Validation
# ==============================================================================

health: ## Check API health (local server)
	$$r = Invoke-RestMethod -Uri http://localhost:8000/health -Method GET; $$r | ConvertTo-Json -Depth 5

health-hf: ## Check API health (Hugging Face Spaces deployment)
	$$r = Invoke-RestMethod -Uri https://thewhitenigs-spectre-backend.hf.space/health -Method GET -TimeoutSec 60; $$r | ConvertTo-Json -Depth 5

env-check: ## Validate all development dependencies are installed
	powershell -ExecutionPolicy Bypass -File scripts/audit-test-deps.ps1



# ==============================================================================
# Composite Workflows
# ==============================================================================

bootstrap: install docker-up migrate seed ## Full project setup (install + infra + DB + seed)
	@echo "Bootstrap complete. Run 'make dev-win' to start server."

reset: docker-down clean seed-reset ## Full teardown (stop services, clear caches, reset seeds)
	@echo "Reset complete. Run 'make bootstrap' to rebuild."

ci: check test-cov ## CI pipeline (lint + typecheck + tests + coverage)

# ==============================================================================
# Maintenance & Continuity
# ==============================================================================

infra-status: ## Show status of HF Spaces and Supabase projects
	python deploy.py --inspect
	npx supabase projects list

wakeup-logs: ## View logs of the latest keep-alive GitHub Action run
	$$run_id = gh run list --workflow="keepalive.yml" --limit 1 --json databaseId --jq '.[0].databaseId'; if ($$run_id) { gh run view $$run_id --log } else { Write-Host "No runs found." }

wakeup-trigger: ## Manually trigger the keep-alive workflow and watch progress
	gh workflow run "Keep HF Space Alive"; Start-Sleep -Seconds 2; gh run watch

heartbeat-list: ## Show the latest 10 heartbeat records from Supabase
	$$URL = "postgresql://postgres.rgnyrswxydfuqldeeqsg:ZikriSpectre2026%21%23@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"; psql $$URL -c "SELECT * FROM keepalive_ping ORDER BY pinged_at DESC LIMIT 10;"

db-query: ## Execute arbitrary SQL (usage: make db-query SQL="SELECT * FROM users")
	@$$URL = "postgresql://postgres.rgnyrswxydfuqldeeqsg:ZikriSpectre2026%21%23@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"; psql $$URL -c "$(SQL)"

db-tables: ## List all tables in the remote database
	@$$URL = "postgresql://postgres.rgnyrswxydfuqldeeqsg:ZikriSpectre2026%21%23@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"; psql $$URL -c "\dt"

# ==============================================================================
# Cleanup
# ==============================================================================

clean-pyc: ## Remove __pycache__ directories
	Get-ChildItem -Path . -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

clean: ## Remove all build artifacts and caches
	Get-ChildItem -Path . -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
	Get-ChildItem -Path . -Recurse -Directory -Filter '.pytest_cache' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
	Get-ChildItem -Path . -Recurse -Directory -Filter '.mypy_cache' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
	Get-ChildItem -Path . -Recurse -Directory -Filter 'htmlcov' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
	Remove-Item -Force .coverage -ErrorAction SilentlyContinue
	Remove-Item -Force .coverage -ErrorAction SilentlyContinue


