# Lightweight Makefile for separated backend/frontend development

PY ?= python
HOST ?= 127.0.0.1
PORT ?= 8010
FRONTEND_HOST ?= 127.0.0.1
FRONTEND_PORT ?= 5173
BACKEND_DIR ?= backend
FRONTEND_DIR ?= frontend

.PHONY: help setup setup-full migrate seed run-backend run-frontend run-full run \
	test lint format typecheck check

help: ## Show available targets
	@$(PY) -c "import re, pathlib; p=pathlib.Path('Makefile'); lines=p.read_text(encoding='utf-8').splitlines(); out=[]; [out.append(m.groups()) for line in lines if (m:=re.match(r'^([a-zA-Z0-9_-]+):.*##\s+(.*)$$', line))]; width=max([len(k) for k,_ in out], default=0); print('Targets:'); [print(f'  {k.ljust(width)}  {v}') for k,v in out]"

setup: ## Install backend Python dependencies
	$(PY) -m pip install -e .[dev]

setup-full: setup ## Install backend and frontend dependencies
	cd $(FRONTEND_DIR) && npm install

migrate: ## Run Django migrations
	cd $(BACKEND_DIR) && $(PY) manage.py makemigrations && $(PY) manage.py migrate

seed: ## Seed workflow templates and sample agents
	cd $(BACKEND_DIR) && $(PY) manage.py seed_workflows

run-backend: ## Run Django backend API
	cd $(BACKEND_DIR) && $(PY) manage.py runserver $(HOST):$(PORT)

run-frontend: ## Run React frontend app
	cd $(FRONTEND_DIR) && npm run dev -- --host $(FRONTEND_HOST) --port $(FRONTEND_PORT)

run-full: ## Run backend and frontend together
	@$(PY) scripts/run_full.py \
		--backend-dir $(BACKEND_DIR) \
		--frontend-dir $(FRONTEND_DIR) \
		--host $(HOST) \
		--port $(PORT) \
		--frontend-host $(FRONTEND_HOST) \
		--frontend-port $(FRONTEND_PORT)


test: ## Run test suite
	$(PY) -m pytest

lint: ## Run Ruff lint checks
	$(PY) -m ruff check backend tests

format: ## Run Ruff formatter
	$(PY) -m ruff format backend tests

typecheck: ## Run mypy type checks
	$(PY) -m mypy backend

check: test lint typecheck ## Run all quality checks
