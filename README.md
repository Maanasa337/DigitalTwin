# TwinVoice

Voice-driven industrial digital twin and predictive-maintenance platform with explainable AI. Fully open source, runs on one laptop.
Requirements: [docs/PRD.md](docs/PRD.md) · Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

**Status:** modules M0 (platform core), M1 (sensor simulator), M2 (digital twin: registry, Ditto sync, AAS/DTDL/NGSI-LD, hierarchy, T3 write-back, lifecycle), M3 (telemetry ingest and alarms), M4 (asset health), M5 (prediction and model registry), M6 (explainable AI), M7 (maintenance scheduling), M8 (production and energy analytics) and M11 (edge runner) are implemented, together with the 3D twin and plant layout (FR-DT-06/07), the benchmark runner (FR-PM-09), ONNX export (FR-EDGE-01) and Grafana embedding (FR-MM-05).

Inference: every asset is scored by its asset type's trained production model. The edge runner scores the assets it is bound to; the 30 s server job (`workers/tasks/infer.py`, via `modules/pdm/scoring.py`) scores the rest with the same bundle, and takes an asset over when its edge runner goes quiet for 2 minutes. Server windows are raw telemetry in 10 s buckets, the period the models were trained on. Trained metrics the platform does not store as sensors (`speed_pct`, `power_factor`, `cycle_time_s`) are filled with their training median and flagged `imputed_features` on the prediction. Global importance, partial dependence and explanation-quality metrics are computed after training, hourly for production models, and on demand from `/explain/quality`.

Known gaps: MetroPT-3 detection has 0 h lead time (see `benchmarks/README.md`).

## Quickstart

Prerequisites: Docker Desktop (or Docker Engine + Compose v2), ~8 GB RAM for Docker.

```bash
cp .env.example .env          # optional: change ports / enable T3 write-back
docker compose up -d --build  # first start pulls ~4 GB of images
docker compose exec api python -m app.seed   # plant, lines, 10 machines, failure modes, scenarios, Ditto twins
```

| URL | What |
|---|---|
| http://localhost:8088 | Web app (log in as below) |
| http://localhost:8000/docs | API (OpenAPI) — `http://localhost:8000/api/v1/health` shows every dependency |
| http://localhost:8081 | Keycloak (master admin: `admin` / `admin`) |
| opc.tcp://localhost:4840/twinvoice/ | Simulator OPC UA server (e.g. UaExpert) |
| localhost:5020 | Simulator Modbus TCP |
| localhost:1883 | MQTT (Sparkplug B `spBv1.0/plant-01/DDATA/...`; edge predictions on `twinvoice/pred/{asset}`) |
| http://localhost:8088/grafana/ | Grafana (anonymous read-only; admin `admin` / `GRAFANA_ADMIN_PASSWORD`). Dashboards "Fleet overview" and "Asset overview" |

After seeding, train real models (writes bundles with ONNX to `data/models/`) and optionally run the benchmark and the edge runner:

```bash
make train            # bootstrap: one RUL model per asset type (simulator data) + C-MAPSS FD001, promoted to production
python data/download.py cmapss ai4i metropt3   # once, for benchmarks
make benchmark        # C-MAPSS FD001-4, AI4I 2020, MetroPT-3 -> benchmarks/results/<date>.md (also runnable from /models/benchmarks)
make edge             # docker compose --profile edge up -d edge: ONNX + local TreeSHAP, publishes twinvoice/pred/{asset}
```

Demo users (realm `twinvoice`, password `twinvoice` for all):

| User | Role | T3 PIN |
|---|---|---|
| `ravi` | technician | — |
| `priya` | manager | — |
| `marcus` | engineer | `246810` |
| `admin` | admin | `135790` |

Twin write-back commands (`set_load`, `set_speed`, `maintenance_reset`) are risk tier T3: they need `TV_ALLOW_T3=true` in `.env` **and** the user's PIN.

## Repository

```
apps/api          FastAPI modules M0-M10, ingest (Sparkplug + edge predictions), Celery workers (infer, explain, train, benchmark, reports); Alembic
apps/simulator    SimPy machines + degradation physics; Sparkplug B, OPC UA, Modbus; scenarios, replay, export
apps/edge         Edge runner: MQTT -> features -> ONNX Runtime -> local TreeSHAP -> twinvoice/pred, SQLite store-and-forward
apps/web          React 19 + Ant Design 5 + ECharts + React Three Fiber (3D twin, plant layout), Grafana embed
packages/contracts  Sparkplug B codec + shared EdgePrediction schema
packages/pdm      Features, anomaly/failure/RUL models, conformal intervals, ONNX export, model bundles, benchmark library
packages/xai      SHAP/EBM attribution, counterfactuals, reason cards, narration audit
packages/nlu      Intent router, tiers, slots for voice/chat
benchmarks/       run.py CLI + results/*.md
infra/            Postgres init, Mosquitto, Keycloak realm + login theme, Grafana provisioning
data/             download.py for public datasets; synthetic exports, models, benchmark reports (nothing committed)
```

## Development

Python projects use [uv](https://docs.astral.sh/uv/), the web app uses pnpm. `make <target>` wraps the commands below.

```bash
# API (needs the compose postgres on 127.0.0.1:5433 for tests)
cd apps/api && uv run pytest && uv run ruff check app alembic tests && uv run mypy app

# Simulator, edge and packages
cd apps/simulator && uv run pytest
cd apps/edge && uv run pytest
cd packages/contracts && uv run pytest   # likewise packages/pdm, packages/xai, packages/nlu

# Web (dev server on :5173 proxies /api and /ws to localhost:8000, /grafana to localhost:3000)
cd apps/web && pnpm install && pnpm dev
pnpm typecheck && pnpm lint && pnpm test && pnpm build
```

`docker-compose.override.yml` (applied automatically) hot-reloads the API from `apps/api/app` and publishes the Ditto gateway (`127.0.0.1:8080`) and the simulator control API (`127.0.0.1:8090`) for debugging.

## Licence

Apache-2.0. All runtime dependencies are OSI-licensed; see PRD §11–12 for the licence audit.
