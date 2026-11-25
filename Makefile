.PHONY: install verify lint typecheck test pyodide-check web-check format

install:  ## Install Python and web dependencies exactly as locked
	uv sync --all-packages --locked
	npm ci --prefix engine/pyodide
	npm ci --prefix web

verify: lint typecheck test pyodide-check web-check  ## Everything CI runs; must pass before work is called done

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

web-check:
	npm run check --prefix web
	npm run lint --prefix web
	npm test --prefix web
	npm run build --prefix web

format:
	uv run ruff format .
	uv run ruff check --fix .
	npm run format --prefix web
