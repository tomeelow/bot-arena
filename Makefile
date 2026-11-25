.PHONY: install verify lint typecheck test web-check format

install:  ## Install Python and web dependencies exactly as locked
	uv sync --all-packages --locked
	npm ci --prefix web

verify: lint typecheck test web-check  ## Everything CI runs; must pass before work is called done

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports

typecheck:
	uv run pyright

test:
	uv run pytest

web-check:
	npm run check --prefix web
	npm run lint --prefix web
	npm test --prefix web
	npm run build --prefix web

format:
	uv run ruff format .
	uv run ruff check --fix .
	npm run format --prefix web
