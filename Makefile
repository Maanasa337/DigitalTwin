# TwinVoice developer commands. On Windows without `make`, run the commands under each target directly.
COMPOSE ?= docker compose

.PHONY: up down seed logs train benchmark benchmark-quick edge test test-api test-sim test-contracts test-xai test-nlu test-pdm test-edge test-web lint

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

seed:
	$(COMPOSE) exec api python -m app.seed

logs:
	$(COMPOSE) logs -f --tail=100 api simulator

# M5: train and promote one RUL model per asset type (on data/synthetic; the simulator is asked for
# an export if there is none) plus C-MAPSS FD001. Bundles land in data/models/{name}/{version}/.
train:
	$(COMPOSE) exec worker python -m app.workers.tasks.train --bootstrap

# FR-PM-09: needs data/raw (python data/download.py cmapss ai4i metropt3). Writes data/benchmarks/<date>.md
# and a benchmark_runs row. DATASETS=FD001,AI4I to run fewer.
DATASETS ?= FD001,FD002,FD003,FD004,AI4I,METROPT3
benchmark:
	$(COMPOSE) exec worker python /app/benchmarks/run.py --datasets $(DATASETS) --out /data/benchmarks

benchmark-quick:
	$(COMPOSE) exec worker python /app/benchmarks/run.py --datasets $(DATASETS) --quick --out /data/benchmarks

# M11: the edge runner, after `make train` (it serves the newest data/models bundle per asset).
edge:
	$(COMPOSE) --profile edge up -d --build edge

test: test-contracts test-nlu test-pdm test-xai test-sim test-edge test-api test-web

# Needs the compose `postgres` service (database twinvoice_test on 127.0.0.1:5433).
test-api:
	cd apps/api && uv run pytest

test-sim:
	cd apps/simulator && uv run pytest

test-contracts:
	cd packages/contracts && uv run pytest

test-xai:
	cd packages/xai && uv run pytest

test-nlu:
	cd packages/nlu && uv run pytest

test-pdm:
	cd packages/pdm && uv run pytest

test-edge:
	cd apps/edge && uv run pytest

test-web:
	cd apps/web && pnpm test

lint:
	cd apps/api && uv run ruff check app alembic tests && uv run ruff format --check app alembic tests && uv run mypy app
	cd apps/simulator && uv run ruff check . && uv run ruff format --check .
	cd packages/contracts && uv run ruff check . && uv run ruff format --check .
	cd packages/xai && uv run ruff check .
	cd packages/nlu && uv run ruff check .
	cd packages/pdm && uv run ruff check .
	cd apps/edge && uv run ruff check . && uv run ruff format --check .
	cd apps/web && pnpm typecheck && pnpm lint
