.PHONY: install verify lint typecheck test pyodide-check sandbox-check web-check format dev-api

install:  ## Install Python and web dependencies exactly as locked
	uv sync --all-packages --locked
	npm ci --prefix engine/pyodide
	npm ci --prefix web

verify: lint typecheck test pyodide-check sandbox-check web-check  ## Everything CI runs; must pass before work is called done

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports

typecheck:
	uv run pyright

test:
	uv run pytest

pyodide-check:  ## The golden games must replay to the same hashes inside Pyodide
	npm run check --prefix engine/pyodide

sandbox-check:  ## The ranked jail and its adversarial suite, in Linux (needs Docker running)
	@docker info >/dev/null 2>&1 || { echo "sandbox-check needs Docker running"; exit 1; }
	docker build -q -f sandbox/Dockerfile -t arena-sandbox .
	docker run --rm --privileged arena-sandbox pytest -q sandbox/tests

web-check:
	npm run check --prefix web
	npm run lint --prefix web
	npm test --prefix web
	npm run build --prefix web

format:
	uv run ruff format .
	uv run ruff check --fix .
	npm run format --prefix web

dev-api:  ## Local API + worker on 127.0.0.1:8000 with a fake login; pair with `npm run dev --prefix web`
	uv run python scripts/dev_server.py
