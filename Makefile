# InsurAgent — tareas de desarrollo.
# El intérprete se toma del venv del diplomado salvo que se pase PY=...
PY ?= "$(CURDIR)/../../bin/python"
SRC = src/insuragent

.DEFAULT_GOAL := help

help: ## Muestra esta ayuda
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Instala dependencias en el venv activo
	$(PY) -m pip install -r requirements.txt

seed: ## Genera datos sintéticos y puebla SQLite
	$(PY) scripts/seed_db.py

index: ## Vectoriza las condiciones generales en FAISS
	$(PY) scripts/build_index.py

eval: ## Corre el set de preguntas doradas y reporta métricas (PRD §5)
	$(PY) scripts/run_eval.py

app: ## Levanta la interfaz Streamlit
	$(PY) -m streamlit run $(SRC)/ui/app.py

test: ## Ejecuta la suite de pruebas
	$(PY) -m pytest

lint: ## Linter + formato
	$(PY) -m ruff check src tests scripts
	$(PY) -m ruff format --check src tests scripts

fmt: ## Aplica formato
	$(PY) -m ruff format src tests scripts
	$(PY) -m ruff check --fix src tests scripts

report: ## Genera el reporte técnico en PDF (docs/report.pdf)
	$(PY) scripts/build_report.py

bootstrap: seed index ## Prepara todos los artefactos locales

clean: ## Borra artefactos generados
	rm -rf data/index data/insuragent.db data/traces.jsonl .pytest_cache .ruff_cache

.PHONY: help install seed index eval app test lint fmt report bootstrap clean
