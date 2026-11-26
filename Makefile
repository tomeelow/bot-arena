.PHONY: install verify lint typecheck test rl-check pyodide-check sandbox-check deploy-check web-check web-e2e format dev-api

install:  ## Install Python and web dependencies exactly as locked
	uv sync --all-packages --locked
	uv sync --project rl --locked
	npm ci --prefix engine/pyodide
	npm ci --prefix web
	cd web && npx playwright install --with-deps chromium

verify: lint typecheck test rl-check pyodide-check sandbox-check deploy-check web-check web-e2e  ## Everything CI runs; must pass before work is called done

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports

typecheck:
	uv run pyright

test:
	uv run pytest

rl-check:  ## Boss training (rl/, its own project so numpy stays off the server): types and tests
	cd rl && uv run --locked pyright && uv run --locked pytest -q

pyodide-check:  ## The golden games must replay to the same hashes inside Pyodide
	npm run check --prefix engine/pyodide

sandbox-check:  ## The ranked jail and its adversarial suite, in Linux (needs Docker running)
	@docker info >/dev/null 2>&1 || { echo "sandbox-check needs Docker running"; exit 1; }
	docker build -q -f sandbox/Dockerfile -t arena-sandbox .
	docker run --rm --privileged arena-sandbox pytest -q sandbox/tests

deploy-check:  ## deploy/Caddyfile in Debian 13's Caddy: only the Pages proxy gets through (needs Docker)
	@docker info >/dev/null 2>&1 || { echo "deploy-check needs Docker running"; exit 1; }
	./deploy/check-caddy.sh

web-check:
	npm run check --prefix web
	npm run lint --prefix web
	npm test --prefix web
	npm run build --prefix web

web-e2e:  ## Browser practice in a real browser: same replays as the CLI, hung bots stopped
	npm run e2e --prefix web

format:
	uv run ruff format .
	uv run ruff check --fix .
	npm run format --prefix web

dev-api:  ## Local API + worker on 127.0.0.1:8000 with a fake login; pair with `npm run dev --prefix web`
	uv run python scripts/dev_server.py
