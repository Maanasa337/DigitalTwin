# TwinVoice

Voice-driven industrial digital twin and predictive-maintenance platform with explainable AI. Fully open source, runs on one laptop.
Requirements: [docs/PRD.md](docs/PRD.md) · Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

**Status:** modules M0 (platform core), M1 (sensor simulator), M2 (digital twin: registry, Ditto sync, AAS/DTDL/NGSI-LD, hierarchy, T3 write-back, lifecycle), M3 (telemetry ingest and alarms), M4 (asset health), M5 (prediction and model registry), M6 (explainable AI), M7 (maintenance scheduling) and M8 (production and energy analytics) are implemented.

Not yet built: the 3D twin and plant layout (FR-DT-06/07), the benchmark runner (FR-PM-09), ONNX export and the edge runner (FR-EDGE-01/02), and Grafana embedding (FR-MM-05).

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
| localhost:1883 | MQTT (Sparkplug B `spBv1.0/plant-01/DDATA/...`) |

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
apps/api          FastAPI: core (auth, audit, errors, WS hub), assets, twin, simulation proxy; Alembic migrations
apps/simulator    SimPy machines + degradation physics; Sparkplug B, OPC UA, Modbus; scenarios, replay, export
apps/web          React 19 + Ant Design 5: app shell, /twin, /simulation
packages/contracts  Sparkplug B protobuf codec shared by simulator and (later) ingest
infra/            Postgres init, Mosquitto, Keycloak realm
data/             download.py for public datasets; synthetic exports land in data/synthetic
```

## Development

Python projects use [uv](https://docs.astral.sh/uv/), the web app uses pnpm. `make <target>` wraps the commands below.

```bash
# API (needs the compose postgres on 127.0.0.1:5433 for tests)
cd apps/api && uv run pytest && uv run ruff check app alembic tests && uv run mypy app

# Simulator and contracts
cd apps/simulator && uv run pytest
cd packages/contracts && uv run pytest

# Web (dev server on :5173 proxies /api and /ws to localhost:8000)
cd apps/web && pnpm install && pnpm dev
pnpm typecheck && pnpm lint && pnpm test && pnpm build
```

`docker-compose.override.yml` (applied automatically) hot-reloads the API from `apps/api/app` and publishes the Ditto gateway (`127.0.0.1:8080`) and the simulator control API (`127.0.0.1:8090`) for debugging.

## Licence

Apache-2.0. All runtime dependencies are OSI-licensed; see PRD §11–12 for the licence audit.
