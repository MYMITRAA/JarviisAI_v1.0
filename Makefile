# ============================================================
# JarviisAI — Developer Makefile
# Usage: make <target>
# ============================================================

.PHONY: help up down build restart logs shell-auth shell-db migrate test clean

# ── Colors ───────────────────────────────────────────────────
CYAN  := \033[0;36m
GREEN := \033[0;32m
RESET := \033[0m

help: ## Show this help
	@echo ""
	@echo "  $(CYAN)JarviisAI — Developer Commands$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ── Docker ────────────────────────────────────────────────────
up: ## Start all services (dev mode with hot reload)
	@echo "$(CYAN)Starting JarviisAI stack...$(RESET)"
	docker compose up

up-d: ## Start all services in background
	docker compose up -d

down: ## Stop all services
	docker compose down

build: ## Rebuild all images
	docker compose build --no-cache

restart: ## Restart a specific service: make restart s=auth-service
	docker compose restart $(s)

logs: ## Tail logs for a service: make logs s=auth-service
	docker compose logs -f $(s)

# ── Shells ────────────────────────────────────────────────────
shell-auth: ## Open shell in auth service container
	docker compose exec auth-service bash

shell-projects: ## Open shell in projects service container
	docker compose exec projects bash

shell-deploy: ## Open shell in deploy service container
	docker compose exec deploy bash

shell-ai: ## Open shell in AI orchestrator container
	docker compose exec ai-orchestrator bash

shell-sso: ## Open shell in SSO service container
	docker compose exec sso bash

shell-billing: ## Open shell in billing service container
	docker compose exec billing bash

shell-db: ## Open psql in postgres container
	docker compose exec postgres psql -U jarviis -d jarviisdb

shell-redis: ## Open redis-cli
	docker compose exec redis redis-cli -a redis_secret

logs-all: ## Tail logs for ALL services
	docker compose logs -f --tail=50

# ── Database ──────────────────────────────────────────────────
migrate: ## Run Alembic migrations
	docker compose exec auth-service alembic upgrade head

migrate-create: ## Create new migration: make migrate-create msg="add users table"
	docker compose exec auth-service alembic revision --autogenerate -m "$(msg)"

migrate-down: ## Rollback last migration
	docker compose exec auth-service alembic downgrade -1

# ── Testing ───────────────────────────────────────────────────
test: ## Run all service tests
	@echo "$(CYAN)Running Auth Service tests...$(RESET)"
	cd services/auth && pip install aiosqlite pytest-asyncio -q && pytest app/tests/ -v
	@echo "$(CYAN)Running Frontend type-check...$(RESET)"
	cd frontend && npm run type-check

test-auth: ## Run auth service tests only
	cd services/auth && pytest app/tests/ -v --cov=app --cov-report=term-missing

test-watch: ## Run auth tests in watch mode
	cd services/auth && pytest app/tests/ -v -f

# ── Frontend ──────────────────────────────────────────────────
fe-install: ## Install frontend npm dependencies
	cd frontend && npm install

fe-dev: ## Run frontend dev server locally (without Docker)
	cd frontend && npm run dev

fe-build: ## Build frontend for production
	cd frontend && npm run build

fe-lint: ## Lint frontend code
	cd frontend && npm run lint

# ── Utilities ────────────────────────────────────────────────
clean: ## Remove all containers, volumes, and node_modules
	docker compose down -v --remove-orphans
	find . -name "node_modules" -type d -prune -exec rm -rf {} +
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find . -name ".next" -type d -prune -exec rm -rf {} +
	@echo "$(GREEN)Clean complete$(RESET)"

setup: ## First-time setup: copy .env, install deps
	@cp -n .env.example .env && echo "$(GREEN).env created from .env.example$(RESET)" || echo ".env already exists"
	@echo "$(CYAN)Edit .env and fill in your JWT_SECRET and SECRET_KEY$(RESET)"
	@echo "$(CYAN)Then run: make up$(RESET)"

ps: ## Show running container status
	docker compose ps
