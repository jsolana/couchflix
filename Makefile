.DEFAULT_GOAL := help
.PHONY: help run build install rebuild test unit e2e screenshots env clean-db clean reset

help: ## Muestra esta ayuda
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36mmake %-12s\033[0m %s\n", $$1, $$2}'

run: ## Arranca COUCHFLIX (crea entorno y BD si hace falta)
	./couchflix

build: ## Genera el binario autónomo dist/couchflix (no se sube al repo)
	@test -x .venv/bin/python || ./couchflix test --collect-only -q >/dev/null
	@.venv/bin/python -c "import PyInstaller" 2>/dev/null || (command -v uv >/dev/null && uv pip install -q --python .venv/bin/python -e ".[build]" || .venv/bin/python -m pip install -q -e ".[build]")
	.venv/bin/python -m PyInstaller --noconfirm --clean --onefile --name couchflix \
		--distpath dist --workpath build --specpath build \
		--add-data "$(CURDIR)/couchflix_app/web/static:couchflix_app/web/static" \
		--add-data "$(CURDIR)/couchflix_app/infrastructure/migrations:couchflix_app/infrastructure/migrations" \
		--exclude-module couchflix_app.infrastructure.providers.fake \
		scripts/entry.py
	@echo "\n✔ Binario: dist/couchflix  (ejecútalo desde una carpeta con tu .env; la BD se crea en ./data)"

install: ## Crea .venv e instala dependencias (incluye pruebas y Chromium)
	./couchflix test --collect-only -q >/dev/null

rebuild: ## Recrea el entorno desde cero (borra .venv) y reinstala
	rm -rf .venv
	$(MAKE) install

test: ## Pruebas unitarias + aceptación Playwright (sin Internet)
	./couchflix test

unit: ## Solo pruebas unitarias
	./couchflix test tests/unit

e2e: ## Solo pruebas de aceptación Playwright
	./couchflix test tests/e2e

screenshots: ## Regenera docs/screenshots
	./couchflix test -m screenshots

env: ## Crea .env desde .env.example (si no existe)
	@test -f .env && echo ".env ya existe" || (cp .env.example .env && echo ".env creado: edítalo con tus claves")

clean-db: ## Elimina la base de datos local (pierdes historial y valoraciones)
	rm -rf data

clean: ## Elimina cachés y artefactos de build/test, incluido dist/ (conserva .venv y datos)
	rm -rf .pytest_cache test-results build dist *.egg-info
	find . -name __pycache__ -not -path './.venv/*' -prune -exec rm -rf {} +

reset: clean clean-db ## Limpia todo salvo .venv y .env
