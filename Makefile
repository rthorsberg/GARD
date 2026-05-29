COMPOSE       ?= docker compose -f deploy/docker-compose.yml
API_PORT      ?= 8080
API_BASE      ?= http://127.0.0.1:$(API_PORT)
PYTHON        ?= python3

.DEFAULT_GOAL := help

.PHONY: help up up-build down down-volumes restart logs ps seed reset token \
        test test-integration lint

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Start the local stack (no rebuild)
	$(COMPOSE) up -d

up-build: ## Build images and start the stack
	$(COMPOSE) up -d --build

down: ## Stop the stack, keep the Postgres volume
	$(COMPOSE) down

down-volumes: ## Stop the stack AND wipe the Postgres volume
	$(COMPOSE) down -v

restart: ## Restart all services
	$(COMPOSE) restart

logs: ## Tail the API logs
	$(COMPOSE) logs -f api

ps: ## Show stack status
	$(COMPOSE) ps

seed: ## Mint a dev token and import the default device fixture
	@./deploy/scripts/seed.sh

reset: down-volumes up-build ## Wipe DB, rebuild image, restart stack
	@echo "Waiting for stack to settle..."
	@sleep 4
	@$(MAKE) -s seed

token: ## Mint a fresh dev token (subject=ops@example.com, ttl=2h)
	@$(COMPOSE) exec -T api python -m gard issue-token \
		--subject ops@example.com --role lifecycle_manager --ttl-seconds 7200

test: ## Run the test suite against the running Postgres
	@GARD_DATABASE_URL=postgresql+psycopg://gard:gard@127.0.0.1:5432/gard \
	 GARD_JWT_SECRET=dev-only-do-not-use-in-prod \
	 $(PYTHON) -m pytest -q

lint: ## Ruff format check + lint
	@ruff format --check gard tests
	@ruff check gard tests
