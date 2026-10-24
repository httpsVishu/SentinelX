# ==============================================================================
# SentinelX: convenience commands for local development
# ==============================================================================

.PHONY: help up down build restart logs \
        backend-shell frontend-shell db-shell \
        migrate migration seed \
        test test-frontend \
        fmt lint clean

help:
	@echo "SentinelX Makefile"
	@echo ""
	@echo "  make up              Start the full stack (build if needed)"
	@echo "  make down            Stop the stack"
	@echo "  make build           Rebuild all images"
	@echo "  make restart         Restart all services"
	@echo "  make logs            Tail logs for all services"
	@echo ""
	@echo "  make backend-shell   Open a shell inside the backend container"
	@echo "  make frontend-shell  Open a shell inside the frontend container"
	@echo "  make db-shell        Open a psql shell inside the postgres container"
	@echo ""
	@echo "  make migrate         Apply Alembic migrations (upgrade head)"
	@echo "  make migration msg=\"...\"  Autogenerate a new Alembic migration"
	@echo "  make seed            Populate demo data (department, admin, vendors, sites)"
	@echo ""
	@echo "  make test            Run the backend tests (uses a separate sentinelx_test database)"
	@echo "  make test-frontend   Run the frontend tests"
	@echo "  make fmt             Format backend code"
	@echo "  make lint            Lint backend code"
	@echo "  make clean           Remove containers and volumes"

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

restart:
	docker compose restart

logs:
	docker compose logs -f

backend-shell:
	docker compose exec backend sh

frontend-shell:
	docker compose exec frontend sh

db-shell:
	docker compose exec postgres psql -U $${POSTGRES_USER:-sentinelx} -d $${POSTGRES_DB:-sentinelx}

migrate:
	docker compose exec backend alembic upgrade head

migration:
	docker compose exec backend alembic revision --autogenerate -m "$(msg)"

seed:
	docker compose exec backend python -m app.seed.seed_data

test:
	docker compose exec backend pytest -v

test-frontend:
	docker compose exec frontend npm run test

fmt:
	docker compose exec backend ruff format app tests

lint:
	docker compose exec backend ruff check app tests

clean:
	docker compose down -v --remove-orphans