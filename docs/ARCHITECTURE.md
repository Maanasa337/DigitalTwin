# TwinVoice — Architecture and Implementation Plan

**Voice-Driven Industrial Digital Twin and Predictive Maintenance Platform using Explainable AI**

| Field | Value |
|---|---|
| Document | Architecture & Implementation Plan v1.0 |
| Date | 17 September 2026 |
| Source of requirements | `docs/PRD.md` (FR/NFR IDs referenced throughout), `docs/research/01..03` |
| Cost constraint | Zero paid dependencies. Every component is OSI-licensed or free-to-use and runs on a Windows 11 laptop via Docker Compose. |

---

## Table of Contents

1. Architecture Principles and Decisions
2. Final Technology Stack
3. System Topology and Runtime Services
4. Repository and File Structure
5. Cross-Cutting Conventions (backend, frontend, data, messaging)
6. Contracts: REST, WebSocket, MQTT, shared JSON schemas
7. Database Schema (full DDL)
8. Module Specifications (M0–M11): features, flow, files, APIs, UI
9. UI/UX Specification: theme, palette, typography, layout, components, screens
10. Development Workflow, CI, and Quality Gates
11. Build Phases and Exit Criteria
12. Requirement Traceability (PRD FR-ID → module)

---

## 1. Architecture Principles and Decisions

### 1.1 Principles

1. **One process per concern, one compose file for everything.** Twelve modules, but a single `docker compose up` (NFR-DEP-01). Each module is a Python package or a React feature folder; heavy services (simulator, voice, edge) are separate containers because they have different dependency footprints.
2. **The twin is the source of truth for "now"; Timescale is the source of truth for "then".** Eclipse Ditto holds current state per asset; PostgreSQL/TimescaleDB holds history, predictions, explanations, and all relational data.
3. **Numbers before words.** Every explanation is a JSON object first (SHAP vector, counterfactual, interval). Text and speech are renderings of that object and are audited against it (FR-XAI-07). The LLM never produces a fact that did not come from a tool call (FR-NL-03).
4. **Nothing changes state without a tiered confirmation.** Voice and chat commands carry a risk tier T0–T3; T2/T3 execute only after read-back confirmation and validation against twin state (FR-VN-07).
5. **Same code path for benchmark and live.** The feature pipeline, models, and explainers used by `make benchmark` are the ones used at runtime (FR-PM-01, FR-SIM-08).
6. **Layered backend, mirrored frontend.** Backend `router → service → repository → models/schemas`; frontend `api → hook → page`. No business rules in routers, no SQL in services.
7. **Build the layer when a caller demands it.** No multi-tenancy, no plugin system, no message bus beyond MQTT in v1.

### 1.2 Key decisions (with the alternative rejected)

| Decision | Chosen | Rejected | Reason |
|---|---|---|---|
| Backend language/framework | Python 3.12 + FastAPI | Node/NestJS, Spring Boot | ML, XAI, voice and simulation are all Python; one language for 90 % of the code |
| Twin store | Eclipse Ditto 3.9 | ThingsBoard CE, own tables only | Ditto gives Things, policies, WebSocket change streams and WoT for free; ThingsBoard paywalls edge/forecasting |
| Time-series | TimescaleDB on PostgreSQL 16 | QuestDB, InfluxDB 2 | One database engine for relational + telemetry, continuous aggregates, SQLAlchemy works unchanged |
| Broker | Mosquitto (MQTT 5) | Kafka, NATS | Industrial standard, Sparkplug B, trivial to run on a laptop |
| Frontend | React 18 + Ant Design v5 + Vite | Next.js, Tailwind/shadcn | Developer already works in Ant Design; server rendering is not needed |
| Charts | Apache ECharts 6 | Recharts, Plotly | Dense industrial time-series, dark mode, large datasets, WebGL |
| 3D | React Three Fiber 9 + drei | Babylon.js | Lives inside the React tree; state overlays bind directly to Zustand |
| STT | faster-whisper (CPU INT8) | Vosk, Web Speech API | Accuracy on domain terms; Web Speech API sends audio to Google |
| LLM | Ollama + Qwen3-4B (Apache-2.0) | Llama 3 | Llama licence is not OSI; Qwen3 has native tool calling |
| TTS | Kokoro-82M via sherpa-onnx | Piper (GPL fork), Coqui (non-commercial weights) | Apache-2.0 weights, CPU real-time |
| Scheduler | OR-Tools CP-SAT | Greedy heuristic | Constraint model handles technician/line/tariff constraints cleanly |
| Auth | Keycloak 26 | Own JWT | Roles, OIDC, no password handling in our code |
| Job queue | Celery 5 + Valkey | Django tasks, arq | Beat scheduling for reports, retries for training jobs |

---

## 2. Final Technology Stack

| Layer | Component | Version | Licence | Used by |
|---|---|---|---|---|
| Runtime | Python | 3.12 | PSF | api, simulator, voice, edge, pdm, xai |
| Runtime | Node.js + pnpm | 24 LTS / 9 | MIT | web |
| API | FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.0 (typed), Alembic | 0.14x / 2.x | MIT | api |
| Jobs | Celery 5, Valkey 8 | BSD-3 | api workers |
| Database | PostgreSQL 16 + TimescaleDB Community 2.x | PostgreSQL / Apache + TSL | all |
| Twin store | Eclipse Ditto 3.9 + MongoDB 7 | EPL-2.0 / SSPL (unmodified use) | twin |
| Broker | Eclipse Mosquitto 2.1, paho-mqtt 2 | EPL/EDL | simulator, ingest, edge |
| OPC UA / Modbus | opcua-asyncio 2, pymodbus 3 | LGPL-3 / BSD-3 | simulator |
| Simulation | SimPy 4, NumPy, SciPy | MIT / BSD | simulator |
| ML | scikit-learn 1.9, XGBoost 3, LightGBM 4, PyTorch 2.9, tsfresh, PyOD 3, River, MAPIE 1, lifelines, NASA ProgPy 1.8, MLflow | BSD/Apache/MIT/NOSA | pdm |
| XAI | SHAP 0.52, InterpretML 0.7, DiCE 0.11, Captum 0.9, Quantus | MIT / BSD | xai |
| Voice | faster-whisper 1.2, sherpa-onnx 1.13, Kokoro-82M, openWakeWord 0.6, Pipecat, Ollama 0.33 + Qwen3-4B, spaCy 3.8, rapidfuzz | MIT / Apache / BSD | voice |
| Optimisation | OR-Tools 9 | Apache-2.0 | api (maintenance) |
| Reports | Jinja2, WeasyPrint 69, python-docx, matplotlib | BSD / MIT | api workers |
| Frontend | React 18, TypeScript 5, Vite 6, Ant Design 5, TanStack Query 5, react-router 6, Zustand 5, Apache ECharts 6, React Three Fiber 9, @react-three/drei, i18next | MIT / Apache | web |
| Auth | Keycloak 26 | Apache-2.0 | all |
| Dashboards (optional) | Grafana OSS 13 | AGPL (unmodified) | engineers |
| Edge | ONNX Runtime 1.2x, onnxmltools, whisper.cpp | MIT | edge |
| Tooling | uv, ruff, mypy, pytest, Vitest, Playwright, pip-licenses, license-checker, GitHub Actions | MIT / Apache | CI |

---

## 3. System Topology and Runtime Services

### 3.1 Compose services

| Service | Image / build | Port | Purpose |
|---|---|---|---|
| `postgres` | `timescale/timescaledb-ha:pg16` | 5432 | Relational + telemetry |
| `valkey` | `valkey/valkey:8` | 6379 | Celery broker, cache, WebSocket fan-out pub/sub |
| `mosquitto` | `eclipse-mosquitto:2` | 1883, 9001 (WS) | MQTT broker |
| `mongodb` | `mongo:7` | — | Ditto persistence |
| `ditto` | `eclipse/ditto-*` (gateway, things, policies, connectivity, things-search) | 8080 | Twin store |
| `keycloak` | `quay.io/keycloak/keycloak:26` | 8081 | OIDC, realm imported from `infra/keycloak/realm.json` |
| `ollama` | `ollama/ollama` | 11434 | Local LLM (Qwen3-4B pulled on first start) |
| `api` | `apps/api` | 8000 | FastAPI REST + WebSocket |
| `worker` | `apps/api` (celery worker + beat) | — | Training, reports, KPI rollups |
| `ingest` | `apps/api` (entrypoint `ingest`) | — | MQTT → Timescale → Ditto |
| `simulator` | `apps/simulator` | 4840 (OPC UA), 5020 (Modbus) | Machines, physics, Sparkplug B publisher |
| `voice` | `apps/voice` | 8010 | STT/TTS/router/pipeline (WebSocket audio) |
| `web` | `apps/web` (nginx) | 5173 dev / 80 | React SPA |
| `grafana` | `grafana/grafana-oss:13` | 3000 | Optional engineer dashboards |
| `edge` (profile `edge`) | `apps/edge` | — | ONNX runner, only with `--profile edge` |

### 3.2 Runtime data flow

```
Simulator ──Sparkplug B/MQTT──▶ Mosquitto ──▶ ingest ──▶ TimescaleDB (telemetry hypertable)
                                                 │
                                                 ├──▶ Ditto (PATCH /things/{id}/features)
                                                 └──▶ Valkey pub/sub "live:{asset}" ──▶ api WebSocket hub ──▶ web

worker (every N s per asset) ──▶ pdm.infer(window) ──▶ predictions table ──▶ Ditto feature "prediction"
                                        │
                                        └──▶ xai.explain(prediction) ──▶ explanations table ──▶ narrations (template + LLM + audit)

web voice button ──audio WS──▶ voice service ──▶ STT ──▶ router (spaCy → Ollama tools) ──▶ tier check
        ▲                                                                                   │
        └────────── TTS audio + transcript ◀── narration ◀── api tool call (REST) ◀──── confirm (T2/T3)
```

---

## 4. Repository and File Structure

```
DigitalTwin/
├── docker-compose.yml
├── docker-compose.override.yml          # dev: bind mounts, hot reload
├── Makefile                             # make up / seed / train / benchmark / test / lint
├── .github/workflows/ci.yml
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md                  # this file
│   └── research/
├── infra/
│   ├── postgres/init/001_extensions.sql # timescaledb, pgcrypto, uuid-ossp
│   ├── mosquitto/mosquitto.conf
│   ├── ditto/                           # policies, connection to Mosquitto, WoT models
│   ├── keycloak/realm.json              # realm "twinvoice", clients web/api, roles
│   ├── grafana/provisioning/
│   └── ollama/Modelfile                 # qwen3:4b with system prompt + tools
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   ├── alembic/versions/
│   │   ├── app/
│   │   │   ├── main.py                  # FastAPI app factory, routers, lifespan
│   │   │   ├── core/                    # M0
│   │   │   │   ├── config.py            # pydantic-settings
│   │   │   │   ├── db.py                # engine, session, Base, mixins
│   │   │   │   ├── security.py          # Keycloak JWT verification, get_current_user, require_role
│   │   │   │   ├── audit.py             # write_audit()
│   │   │   │   ├── ws_hub.py            # /ws/live, Valkey subscriber
│   │   │   │   ├── mqtt.py              # shared MQTT client factory
│   │   │   │   ├── ditto.py             # Ditto HTTP client
│   │   │   │   └── errors.py            # problem-details exceptions
│   │   │   ├── common/                  # CrudRepository, CrudService, pagination, schemas
│   │   │   ├── modules/
│   │   │   │   ├── assets/              # M2: plants, lines, assets, components, sensors, AAS
│   │   │   │   ├── twin/                # M2: twin sync, hierarchy, replay, what-if
│   │   │   │   ├── telemetry/           # M3: queries, alarms
│   │   │   │   ├── pdm/                 # M5: models, predictions, training jobs, benchmarks
│   │   │   │   ├── xai/                 # M6: explanations, narration, audit, feedback
│   │   │   │   ├── maintenance/         # M7: work orders, technicians, schedule
│   │   │   │   ├── analytics/           # M8: KPIs, OEE, energy
│   │   │   │   ├── voice/               # M9: sessions, actions, intent execution (tools)
│   │   │   │   ├── reports/             # M10
│   │   │   │   └── simulation/          # M1 control proxy: scenarios, runs
│   │   │   ├── ingest/                  # M3: MQTT consumer entrypoint
│   │   │   └── workers/                 # Celery app, tasks (infer, explain, train, report, kpi)
│   │   └── tests/
│   ├── web/
│   │   ├── package.json, vite.config.ts, tsconfig.json
│   │   ├── src/
│   │   │   ├── app/                     # M0: router, layout shell, theme, auth provider, ws client
│   │   │   ├── lib/                     # axios instance, query client, formatters, echarts theme
│   │   │   ├── api/                     # one file per backend module (generated types + calls)
│   │   │   ├── hooks/                   # use<Resource>.ts (TanStack Query)
│   │   │   ├── store/                   # Zustand: liveTwinStore, voiceStore, uiStore
│   │   │   ├── components/              # shared: StatusTag, HealthGauge, RulBadge, SensorTile, ConfirmReadback, EmptyState, PageHeader
│   │   │   ├── features/
│   │   │   │   ├── monitoring/          # M4
│   │   │   │   ├── twin/                # M2 (3D, AAS viewer, replay, what-if)
│   │   │   │   ├── alarms/              # M3
│   │   │   │   ├── pdm/                 # M5 (models, benchmarks)
│   │   │   │   ├── explain/             # M6
│   │   │   │   ├── maintenance/         # M7
│   │   │   │   ├── analytics/           # M8
│   │   │   │   ├── voice/               # M9
│   │   │   │   ├── reports/             # M10
│   │   │   │   └── simulation/          # M1 control panel
│   │   │   ├── three/                   # machine glTF loaders, overlay materials
│   │   │   └── i18n/                    # en.json, hi.json
│   │   └── public/models/               # CC0 glTF assets
│   ├── simulator/                       # M1
│   │   ├── sim/
│   │   │   ├── machines/                # cnc_mill.py, compressor.py, conveyor.py, hydraulic_press.py, injection_moulder.py
│   │   │   ├── physics/                 # wiener.py, gamma.py, paris_law.py, arrhenius.py, taylor_tool_life.py, motor_efficiency.py, bearing_waveform.py
│   │   │   ├── noise.py, sensors.py, production.py, energy.py
│   │   │   ├── publisher.py             # Sparkplug B encoder + MQTT
│   │   │   ├── opcua_server.py, modbus_server.py
│   │   │   ├── replay.py                # C-MAPSS / MetroPT-3 / AI4I replay
│   │   │   ├── scenarios/*.yaml
│   │   │   ├── export.py                # Parquet with ground-truth RUL + driver labels
│   │   │   └── api.py                   # control endpoints (inject fault, time scale, reset)
│   │   └── tests/
│   ├── voice/                           # M9
│   │   ├── voice/
│   │   │   ├── server.py                # WebSocket audio in / audio+events out
│   │   │   ├── stt.py                   # faster-whisper, hot-words, VAD
│   │   │   ├── wake.py                  # openWakeWord
│   │   │   ├── tts.py                   # Kokoro via sherpa-onnx
│   │   │   ├── router/                  # rules.py (spaCy), llm.py (Ollama tools), slots.py, fuzzy_assets.py
│   │   │   ├── tiers.py                 # T0–T3, confirmation state machine
│   │   │   ├── dialogue.py              # context, referent resolution, timeouts
│   │   │   ├── tools/                   # one function per intent calling api REST
│   │   │   ├── narrate.py               # templates + LLM paraphrase + audit call
│   │   │   └── intents.yaml             # schema + examples (en, hi, hinglish)
│   │   └── tests/                       # 500-utterance suite
│   └── edge/                            # M11
│       ├── runner.py, features.py, onnx_infer.py, treeshap_local.py, buffer.py (SQLite)
│       └── export_models.py
├── packages/
│   ├── pdm/                             # M5 library (importable by api, edge, benchmarks)
│   │   ├── features/  (windows.py, stats.py, spectral.py, energy.py)
│   │   ├── anomaly/   (iforest.py, ecod.py, hst_online.py, drift.py, health_index.py)
│   │   ├── failure/   (gbm.py, ebm.py, logistic.py, calibration.py)
│   │   ├── rul/       (lstm.py, tcn.py, gbm_reg.py, target.py, conformal.py, survival.py, progpy_fusion.py)
│   │   ├── registry/  (mlflow_store.py, onnx_export.py)
│   │   └── datasets/  (cmapss.py, ai4i.py, metropt.py, cwru.py, synthetic.py)
│   ├── xai/                             # M6 library
│   │   ├── attribution/ (tree_shap.py, deep_shap.py, ig.py, temporal.py)
│   │   ├── glassbox/ebm.py
│   │   ├── counterfactual/dice.py
│   │   ├── reason_card.py, knowledge_base/*.yaml
│   │   ├── narration/ (templates.py, llm.py, audit.py)
│   │   ├── confidence.py, quality/ (faithfulness.py, stability.py, truth_agreement.py)
│   │   └── schema.py                    # Explanation JSON model (Pydantic)
│   └── contracts/                       # shared Pydantic models + generated TS (openapi-typescript)
├── benchmarks/                          # runners + results/*.md
├── user_study/                          # questionnaires, task scripts, analysis notebooks
└── data/                                # download.py with checksums; nothing committed
```

---

## 5. Cross-Cutting Conventions

### 5.1 Backend

- **Layers.** `router.py` (HTTP only) → `service.py` (business rules, transactions, audit) → `repository.py` (SQLAlchemy queries) → `models.py` (ORM) + `schemas.py` (Pydantic in/out).
- **Base classes.** `common/repository.py::CrudRepository[Model]` (get, list(paged, filters), create, update, soft_delete) and `common/service.py::CrudService` (wraps repo, calls `write_audit`).
- **Mixins.** `PKMixin` (UUID v4 `id`), `TimestampMixin` (`created_at`, `updated_at`), `SoftDeleteMixin` (`deleted_at`). Master data uses all three; telemetry and event tables use none (append-only, time-keyed).
- **Transactions.** `repo.flush()` → `service.write_audit()` → `session.commit()` in one transaction.
- **Errors.** RFC 7807 problem details; 401 auth, 403 role, 404 missing, 409 conflict (unique/optimistic), 422 validation, 423 locked (T3 second factor missing).
- **Auth.** Keycloak JWT verified with cached JWKS; `get_current_user()` dependency yields `{sub, roles, name}`; `require_role("engineer")` guards. Roles: `technician`, `manager`, `engineer`, `admin`.
- **Pagination.** `?page=1&size=50&sort=-created_at`; response `{items, total, page, size}`.
- **IDs in URLs** are UUIDs; asset **codes** (`cnc-03`) are human keys used by voice and resolved to IDs server-side.
- **Settings** via `pydantic-settings`, env-prefixed `TV_`.

### 5.2 Frontend

- `lib/axios.ts` single instance, base `/api/v1`, bearer token from Keycloak JS adapter, 401 → re-login.
- `api/<module>.ts` typed calls (types generated by `openapi-typescript` into `packages/contracts/ts`).
- `hooks/use<Resource>.ts` wraps TanStack Query; query keys `[module, resource, params]`; live data invalidated by WebSocket events.
- `store/liveTwinStore.ts` (Zustand): `assets: Record<code, LiveAsset>` updated by WS; components subscribe by selector to avoid re-render storms.
- Route per feature: `/`, `/machines`, `/machines/:code`, `/explorer`, `/alarms`, `/twin`, `/twin/3d`, `/twin/replay`, `/twin/what-if`, `/models`, `/models/:id`, `/explain/quality`, `/maintenance`, `/maintenance/schedule`, `/analytics/production`, `/analytics/energy`, `/voice`, `/reports`, `/simulation`.
- Every page renders four states: loading skeleton, empty (`EmptyState`), error (`Result` with retry), data.

### 5.3 Data

- Telemetry is **narrow**: one row per (time, sensor_id). Wide views are built by continuous aggregates and pivots in the API, never by adding columns.
- All timestamps `timestamptz` in UTC; the UI formats in plant timezone (`plants.timezone`).
- Units are stored on `sensors.unit` and echoed in every API payload (`{value, unit}`), never implied.

### 5.4 Messaging

- Sparkplug B topic scheme: `spBv1.0/{plant_code}/DDATA/{line_code}/{asset_code}`; birth/death `NBIRTH/NDEATH/DBIRTH/DDEATH` per spec. Payload metrics named `{component_code}.{sensor_code}` (e.g. `spindle.vib_rms`).
- Commands (twin write-back): `twinvoice/cmd/{asset_code}/{command}` JSON `{command_id, params, issued_by, tier}`; ack on `twinvoice/ack/{asset_code}`.
- Edge predictions: `twinvoice/pred/{asset_code}` JSON = `Prediction` schema (Section 6.4).
- Live fan-out inside the platform: Valkey channel `live:{asset_code}` with `{kind: "telemetry"|"prediction"|"alarm"|"state", payload}`.

---

## 6. Contracts

### 6.1 REST surface (base `/api/v1`)

| Module | Endpoints (method path — purpose) |
|---|---|
| assets (M2) | `GET/POST /plants`, `GET/POST /lines`, `GET/POST/PATCH/DELETE /assets`, `GET /assets/{id}/components`, `GET/POST /components`, `GET /assets/{id}/sensors`, `GET /assets/{id}/aas` (AAS JSON), `GET /assets/{id}/aas.aasx`, `POST /assets/import-aasx`, `GET /assets/{id}/dtdl`, `GET /assets/{id}/ngsi-ld` |
| twin (M2) | `GET /twin/{code}` (Ditto thing merged with latest prediction), `GET /twin/tree` (plant→line→asset→component with health), `POST /twin/{code}/commands` (tiered), `GET /twin/{code}/replay?from&to&step`, `POST /twin/{code}/what-if` → `{run_id}`, `GET /twin/what-if/{run_id}` |
| telemetry (M3) | `GET /telemetry?asset&sensors&from&to&agg=raw|1m|1h`, `GET /telemetry/latest?asset`, `GET /telemetry/export.csv`, `GET /alarms`, `POST /alarms/{id}/ack`, `POST /alarms/{id}/assign`, `POST /alarms/{id}/comment`, `POST /alarms/{id}/shelve`, `GET/POST/PATCH /alarm-rules` |
| pdm (M5) | `GET /models`, `GET /models/{id}`, `POST /models/{id}/promote`, `POST /models/train` (async job), `GET /jobs/{id}`, `GET /predictions?asset&from&to`, `GET /predictions/latest?asset`, `POST /benchmarks/run`, `GET /benchmarks`, `GET /benchmarks/{id}/report.md` |
| xai (M6) | `GET /explanations/{prediction_id}`, `GET /explanations/{id}/counterfactual`, `GET /explanations/{id}/narration?lang=en|hi`, `POST /explanations/{id}/feedback`, `GET /models/{id}/global-importance`, `GET /models/{id}/quality-metrics`, `GET /narration-audits?model` |
| maintenance (M7) | `GET/POST/PATCH /work-orders`, `POST /work-orders/{id}/close`, `GET/POST /technicians`, `GET/POST /technicians/{id}/availability`, `POST /schedules/optimise` → schedule, `GET /schedules/{id}`, `PATCH /schedules/{id}/items/{item_id}` (drag), `GET /work-orders/{id}/risk` |
| analytics (M8) | `GET /kpis?scope=plant|line|asset&id&period=shift|day|week&from&to`, `GET /kpis/definitions`, `GET /oee?...`, `GET /downtime/pareto?...`, `GET /energy/summary?...`, `GET /energy/anomalies?...`, `POST /energy/baselines` |
| voice (M9) | `POST /voice/sessions`, `GET /voice/sessions/{id}`, `POST /voice/actions` (from voice service; executes tool with tier check), `POST /voice/actions/{id}/confirm`, `POST /voice/actions/{id}/cancel`, `POST /chat` (text parity → same router), `GET /voice/intents` (help) |
| reports (M10) | `POST /reports` `{type, scope, period, format}` → job, `GET /reports`, `GET /reports/{id}/file`, `GET/POST /report-schedules` |
| simulation (M1) | `GET /simulation/status`, `POST /simulation/scenario` `{scenario_code}`, `POST /simulation/faults` `{asset, failure_mode, mode: sudden|gradual}`, `POST /simulation/time-scale` `{factor}`, `POST /simulation/reset/{asset}`, `POST /simulation/export` |
| core (M0) | `GET /me`, `GET /health`, `GET /audit?entity&id` |

### 6.2 WebSocket `/ws/live`

Client → server: `{"type":"subscribe","topics":["asset:cnc-03","alarms","voice:session-id"]}` / `unsubscribe`.
Server → client: `{"type":"telemetry","asset":"cnc-03","t":"…","metrics":{"spindle.vib_rms":{"v":2.31,"u":"mm/s"}}}`, `{"type":"prediction",…Prediction}`, `{"type":"alarm",…Alarm}`, `{"type":"state","asset":"cnc-03","state":"DOWN"}`, `{"type":"voice","event":"listening|transcript|confirm_required|executed|spoken","payload":…}`.

### 6.3 Voice service WebSocket `/voice/stream`

Binary frames = 16 kHz PCM audio chunks; text frames = JSON control (`{"type":"ptt_start"}`, `ptt_stop`, `confirm`, `cancel`, `set_lang`). Server emits `{"type":"partial_transcript"}`, `final_transcript`, `intent` (`{name, slots, tier, confidence}`), `readback` (text to confirm), `response` (`{text, audio_b64, citations}`), `error`.

### 6.4 Shared JSON schemas (`packages/contracts`)

```jsonc
// Prediction
{ "id": "uuid", "asset_code": "cnc-03", "component_code": "spindle", "time": "2026-09-17T10:00:00Z",
  "model_version": "rul-gbm-2026.09.1", "health_index": 71.2,
  "failure_probability": { "bearing_wear": 0.62, "overheating": 0.08 },
  "rul": { "point": 38, "low": 29, "high": 47, "unit": "cycles", "coverage": 0.9 },
  "confidence": { "label": "medium", "reasons": ["model_disagreement", "sensor_stuck:temp_2"] },
  "drift": { "flag": false, "score": 0.12 }, "explanation_id": "uuid" }

// Explanation
{ "id": "uuid", "prediction_id": "uuid", "method": "tree_shap", "base_value": 0.11,
  "attributions": [ { "feature": "spindle.vib_rms.slope_6h", "label": "Spindle vibration trend (6 h)",
                      "value": 0.42, "unit": "mm/s per h", "contribution": 0.31, "direction": "higher",
                      "share": 0.48, "rank": 1 } ],
  "ebm_terms": [ { "feature": "...", "contribution": 0.27 } ],
  "agreement": { "shap_vs_ebm_top3_jaccard": 0.67 },
  "counterfactual": { "changes": [ { "feature": "load_pct", "from": 95, "to": 80, "unit": "%" } ],
                      "rul_after": { "point": 61, "low": 50, "high": 70 } , "action": "Reduce feed override" },
  "reason_card": { "symptom": "...", "evidence": ["..."], "likely_cause": "...", "action": "...", "confidence": "medium" } }

// Intent (voice router output)
{ "intent": "create_work_order", "tier": "T2", "confidence": 0.91,
  "slots": { "asset_code": "compressor-02", "task": "replace bearing", "start": "2026-09-20T08:00:00+05:30", "technician": "ravi" },
  "readback": "Creating work order: replace bearing on compressor two, Friday 20 September 08:00, assigned to Ravi. Say confirm or cancel." }
```

---

## 7. Database Schema

PostgreSQL 16 + TimescaleDB. All DDL is applied by Alembic migrations grouped per module (`0001_core`, `0002_assets`, `0003_telemetry`, …). Conventions: `id uuid primary key default gen_random_uuid()`, `created_at/updated_at timestamptz not null default now()`, `deleted_at timestamptz null` on master tables, partial unique indexes `where deleted_at is null`.

### 7.1 Core (M0)

```sql
create table users (
  id uuid primary key default gen_random_uuid(),
  keycloak_sub text not null unique,
  display_name text not null,
  email text,
  roles text[] not null default '{}',
  locale text not null default 'en',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_seen_at timestamptz
);

create table audit_log (
  id bigserial primary key,
  at timestamptz not null default now(),
  actor_id uuid references users(id),
  actor_kind text not null check (actor_kind in ('user','system','voice','edge')),
  entity text not null,            -- table name
  entity_id uuid,
  action text not null,            -- create|update|delete|confirm|execute|ack|...
  before jsonb, after jsonb,
  request_id text, ip text
);
create index on audit_log (entity, entity_id, at desc);
```

### 7.2 Assets and twin (M2)

```sql
create table plants (
  id uuid primary key default gen_random_uuid(),
  code text not null, name text not null,
  timezone text not null default 'Asia/Kolkata',
  grid_emission_factor_kg_per_kwh numeric(8,4) not null default 0.716,
  currency text not null default 'INR',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), deleted_at timestamptz
);
create unique index plants_code_uq on plants(code) where deleted_at is null;

create table lines (
  id uuid primary key default gen_random_uuid(),
  plant_id uuid not null references plants(id),
  code text not null, name text not null, sequence int not null default 0,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), deleted_at timestamptz
);
create unique index lines_code_uq on lines(plant_id, code) where deleted_at is null;

create table assets (
  id uuid primary key default gen_random_uuid(),
  line_id uuid not null references lines(id),
  code text not null, name text not null,
  asset_type text not null check (asset_type in ('cnc_mill','compressor','conveyor','hydraulic_press','injection_moulder','other')),
  manufacturer text, model text, serial_no text, install_date date,
  ditto_thing_id text not null,              -- "twinvoice:cnc-03"
  aas_id text,                               -- IRI
  fidelity_level smallint not null default 2 check (fidelity_level between 1 and 4),
  ideal_cycle_time_s numeric(10,3),
  rated_power_kw numeric(10,3),
  model_3d_path text,                        -- /models/cnc_mill.glb
  position jsonb,                            -- {x,y,z,rot} in plant layout
  status text not null default 'RUNNING' check (status in ('RUNNING','IDLE','DOWN','MAINTENANCE','UNKNOWN')),
  attributes jsonb not null default '{}',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), deleted_at timestamptz
);
create unique index assets_code_uq on assets(code) where deleted_at is null;
create index on assets(line_id);

create table components (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references assets(id),
  code text not null, name text not null,
  component_type text not null,              -- motor|bearing|spindle|pump|belt|heater|valve
  health_weight numeric(4,3) not null default 1.0,
  physics_model text,                        -- wiener|gamma|paris|arrhenius|taylor|none
  physics_params jsonb not null default '{}',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), deleted_at timestamptz
);
create unique index components_code_uq on components(asset_id, code) where deleted_at is null;

create table sensors (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references assets(id),
  component_id uuid references components(id),
  code text not null,                        -- vib_rms
  metric_name text not null,                 -- "spindle.vib_rms" (Sparkplug metric)
  name text not null, unit text not null,
  kind text not null check (kind in ('vibration','temperature','current','voltage','power','pressure','flow','speed','torque','position','count','other')),
  sample_rate_hz numeric(10,3) not null default 1,
  min_valid numeric, max_valid numeric,
  warn_low numeric, warn_high numeric, alarm_low numeric, alarm_high numeric,
  adaptive_sigma numeric(4,2),               -- null = no adaptive alarm
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), deleted_at timestamptz
);
create unique index sensors_metric_uq on sensors(asset_id, metric_name) where deleted_at is null;

create table aas_submodels (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references assets(id),
  semantic_id text not null,                 -- IDTA template IRI
  id_short text not null,                    -- Nameplate|TechnicalData|OperationalData|MaintenanceHistory|PredictiveMaintenance
  version text not null default '1.0',
  content jsonb not null,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create unique index aas_submodels_uq on aas_submodels(asset_id, id_short);

create table failure_modes (
  id uuid primary key default gen_random_uuid(),
  asset_type text not null, code text not null, name text not null,
  component_type text, description text,
  signature jsonb not null,                  -- {metrics:[...], pattern:'trend|spike|level'}
  severity smallint not null default 3 check (severity between 1 and 4),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create unique index failure_modes_uq on failure_modes(asset_type, code);

create table knowledge_base_entries (
  id uuid primary key default gen_random_uuid(),
  failure_mode_id uuid not null references failure_modes(id),
  symptom text not null, likely_cause text not null, recommended_action text not null,
  parts text[] not null default '{}', est_duration_min int, lang text not null default 'en',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
```

### 7.3 Telemetry and events (M3)

```sql
create table telemetry (
  time timestamptz not null,
  sensor_id uuid not null references sensors(id),
  value double precision not null,
  quality smallint not null default 192       -- OPC UA style: 192 good, 64 uncertain, 0 bad
);
select create_hypertable('telemetry','time', chunk_time_interval => interval '1 day');
create index on telemetry (sensor_id, time desc);
alter table telemetry set (timescaledb.compress, timescaledb.compress_segmentby='sensor_id');
select add_compression_policy('telemetry', interval '7 days');

create materialized view telemetry_1m with (timescaledb.continuous) as
  select time_bucket('1 minute', time) as bucket, sensor_id,
         avg(value) as avg, min(value) as min, max(value) as max, stddev(value) as std, count(*) as n
  from telemetry group by bucket, sensor_id;
select add_continuous_aggregate_policy('telemetry_1m', start_offset => interval '2 hours', end_offset => interval '1 minute', schedule_interval => interval '1 minute');
-- telemetry_1h defined identically on 1 hour buckets from telemetry_1m

create table waveforms (
  time timestamptz not null,
  sensor_id uuid not null references sensors(id),
  sample_rate_hz int not null,
  n_samples int not null,
  samples bytea not null,                     -- float32 little-endian
  features jsonb                              -- {rms,kurtosis,crest,bpfo_amp,bpfi_amp,bsf_amp}
);
select create_hypertable('waveforms','time');

create table energy_readings (
  time timestamptz not null,
  asset_id uuid not null references assets(id),
  power_kw double precision not null,
  energy_kwh double precision not null,       -- cumulative meter
  power_factor double precision,
  current_a double precision, voltage_v double precision,
  tariff_rate numeric(10,4)
);
select create_hypertable('energy_readings','time');
create index on energy_readings (asset_id, time desc);

create table production_counts (
  time timestamptz not null,
  asset_id uuid not null references assets(id),
  shift_id uuid,
  good_count int not null default 0, reject_count int not null default 0,
  cycle_time_s double precision, planned boolean not null default true
);
select create_hypertable('production_counts','time');

create table asset_state_events (
  time timestamptz not null,
  asset_id uuid not null references assets(id),
  state text not null check (state in ('RUNNING','IDLE','DOWN','MAINTENANCE','UNKNOWN')),
  cause_code text,                            -- breakdown|changeover|starvation|blocked|planned_maint
  duration_s double precision,                -- filled when next event closes it
  source text not null default 'simulator'
);
select create_hypertable('asset_state_events','time');

create table alarm_rules (
  id uuid primary key default gen_random_uuid(),
  sensor_id uuid references sensors(id),
  asset_id uuid references assets(id),
  kind text not null check (kind in ('threshold','adaptive','ml_anomaly','energy_intensity')),
  params jsonb not null,                      -- {high:..} | {sigma:3, window:'1h'} | {min_score:0.8}
  severity text not null check (severity in ('info','warning','serious','critical')),
  enabled boolean not null default true,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), deleted_at timestamptz
);

create table alarms (
  id uuid primary key default gen_random_uuid(),
  raised_at timestamptz not null default now(),
  cleared_at timestamptz,
  asset_id uuid not null references assets(id),
  sensor_id uuid references sensors(id),
  rule_id uuid references alarm_rules(id),
  severity text not null check (severity in ('info','warning','serious','critical')),
  title text not null, message text not null,
  value double precision, threshold double precision,
  prediction_id uuid,                         -- set for ML alarms
  status text not null default 'active' check (status in ('active','acknowledged','shelved','cleared')),
  acknowledged_by uuid references users(id), acknowledged_at timestamptz,
  assigned_to uuid references users(id),
  shelved_until timestamptz
);
create index on alarms (asset_id, status, raised_at desc);

create table alarm_actions (
  id uuid primary key default gen_random_uuid(),
  alarm_id uuid not null references alarms(id),
  at timestamptz not null default now(),
  actor_id uuid references users(id),
  action text not null check (action in ('ack','assign','comment','shelve','unshelve','clear')),
  note text
);
```

### 7.4 Predictive maintenance (M5)

```sql
create table models (
  id uuid primary key default gen_random_uuid(),
  name text not null,                         -- rul-gbm
  version text not null,                      -- 2026.09.1
  task text not null check (task in ('anomaly','failure','rul','survival')),
  algorithm text not null,                    -- xgboost|lightgbm|ebm|lstm|tcn|iforest|ecod|hst|weibull_aft|progpy
  asset_type text, asset_id uuid references assets(id),   -- global or per-asset
  dataset_ref text not null, dataset_hash text not null,
  feature_set jsonb not null,                 -- ordered feature names
  hyperparams jsonb not null default '{}',
  window_size int, stride int, horizon int,
  artifact_uri text not null,                 -- mlflow:/... or file path
  onnx_uri text, explainer_uri text, calibrator_uri text, conformal_uri text,
  stage text not null default 'candidate' check (stage in ('candidate','production','archived')),
  trained_at timestamptz not null default now(), trained_by uuid references users(id),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create unique index models_name_version_uq on models(name, version);
create unique index models_one_production_uq on models(name, coalesce(asset_id,'00000000-0000-0000-0000-000000000000'::uuid)) where stage='production';

create table model_metrics (
  id uuid primary key default gen_random_uuid(),
  model_id uuid not null references models(id),
  split text not null check (split in ('train','val','test','calibration')),
  metric text not null,                       -- rmse|nasa_score|auc|f1|ece|coverage_90|interval_width|faithfulness|stability
  value double precision not null,
  extra jsonb
);
create index on model_metrics(model_id);

create table predictions (
  id uuid primary key default gen_random_uuid(),
  time timestamptz not null default now(),
  asset_id uuid not null references assets(id),
  component_id uuid references components(id),
  model_id uuid not null references models(id),
  window_start timestamptz not null, window_end timestamptz not null,
  health_index numeric(5,2),
  anomaly_score double precision,
  failure_probability jsonb,                  -- {mode_code: p}
  failure_probability_calibrated jsonb,
  rul_point double precision, rul_low double precision, rul_high double precision,
  rul_unit text default 'cycles', rul_coverage numeric(3,2) default 0.90,
  rul_physics_point double precision, rul_fused_point double precision,
  confidence_label text check (confidence_label in ('high','medium','low')),
  confidence_reasons text[] not null default '{}',
  drift_flag boolean not null default false, drift_score double precision, ood_score double precision,
  source text not null default 'server' check (source in ('server','edge')),
  latency_ms int
);
select create_hypertable('predictions','time');
create index on predictions (asset_id, time desc);

create table benchmark_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(), finished_at timestamptz,
  git_sha text, seed int not null,
  datasets text[] not null,
  results jsonb,                              -- {FD001:{rmse:..,score:..}, AI4I:{auc:..}}
  report_uri text, status text not null default 'running'
);
```

### 7.5 Explainable AI (M6)

```sql
create table explanations (
  id uuid primary key default gen_random_uuid(),
  prediction_id uuid not null,
  created_at timestamptz not null default now(),
  method text not null check (method in ('tree_shap','deep_shap','integrated_gradients','kernel_shap','ebm')),
  base_value double precision,
  attributions jsonb not null,                -- [{feature,label,value,unit,contribution,direction,share,rank}]
  temporal_attribution jsonb,                 -- [[t, weight]] per feature
  ebm_terms jsonb,
  agreement jsonb,                            -- {shap_vs_ebm_top3_jaccard}
  reason_card jsonb,                          -- {symptom,evidence[],likely_cause,action,confidence,kb_entry_id}
  compute_ms int
);
create index on explanations(prediction_id);

create table counterfactuals (
  id uuid primary key default gen_random_uuid(),
  explanation_id uuid not null references explanations(id),
  created_at timestamptz not null default now(),
  target text not null,                       -- 'healthy' | 'rul>=60'
  changes jsonb not null,                     -- [{feature,from,to,unit,actionable}]
  outcome jsonb not null,                     -- {rul_point,rul_low,rul_high} or {p_fail}
  feasibility_score double precision,
  action_text text
);

create table narrations (
  id uuid primary key default gen_random_uuid(),
  explanation_id uuid not null references explanations(id),
  kind text not null check (kind in ('status','why','confidence','counterfactual','report_summary')),
  lang text not null default 'en',
  template_text text not null,
  llm_text text, llm_model text, llm_prompt_hash text,
  final_text text not null,                   -- llm_text if audit passed else template_text
  created_at timestamptz not null default now()
);

create table narration_audits (
  id uuid primary key default gen_random_uuid(),
  narration_id uuid not null references narrations(id),
  rank_agreement double precision not null,   -- top-3 overlap 0..1
  sign_agreement double precision not null,
  numeric_within_tolerance boolean not null,
  hallucinated_features text[] not null default '{}',
  unsupported_recommendation boolean not null default false,
  passed boolean not null,
  details jsonb,
  created_at timestamptz not null default now()
);

create table explanation_feedback (
  id uuid primary key default gen_random_uuid(),
  explanation_id uuid not null references explanations(id),
  user_id uuid references users(id),
  verdict text not null check (verdict in ('agree','disagree','unsure')),
  reason text, suspect_sensor_id uuid references sensors(id),
  channel text not null check (channel in ('ui','voice','chat')),
  created_at timestamptz not null default now()
);

create table explanation_quality_metrics (
  id uuid primary key default gen_random_uuid(),
  model_id uuid not null references models(id),
  method text not null,
  metric text not null,                       -- deletion_auc|insertion_auc|pgi|sensitivity_max|sparsity|truth_top1_agreement|window_jaccard
  value double precision not null,
  dataset_ref text, computed_at timestamptz not null default now()
);
```

### 7.6 Maintenance (M7)

```sql
create table technicians (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id),
  code text not null, name text not null,
  skills text[] not null default '{}',        -- bearing|electrical|hydraulic|cnc
  hourly_cost numeric(10,2),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), deleted_at timestamptz
);
create unique index technicians_code_uq on technicians(code) where deleted_at is null;

create table technician_availability (
  id uuid primary key default gen_random_uuid(),
  technician_id uuid not null references technicians(id),
  starts_at timestamptz not null, ends_at timestamptz not null,
  kind text not null default 'available' check (kind in ('available','leave','training'))
);
create index on technician_availability(technician_id, starts_at);

create table work_orders (
  id uuid primary key default gen_random_uuid(),
  number serial,                              -- human WO-000123
  asset_id uuid not null references assets(id),
  component_id uuid references components(id),
  type text not null check (type in ('corrective','preventive','predictive')),
  priority smallint not null default 3 check (priority between 1 and 5),
  title text not null, description text,
  failure_mode_id uuid references failure_modes(id),
  prediction_id uuid, explanation_id uuid references explanations(id),
  status text not null default 'open' check (status in ('open','scheduled','in_progress','closed','cancelled')),
  planned_start timestamptz, planned_end timestamptz,
  actual_start timestamptz, actual_end timestamptz,
  technician_id uuid references technicians(id),
  parts jsonb not null default '[]',
  est_duration_min int, est_cost numeric(12,2),
  risk_before_slot double precision,          -- P(failure before planned_start)
  created_by uuid references users(id), created_via text not null default 'ui' check (created_via in ('ui','voice','chat','auto')),
  outcome text, prediction_was_correct boolean,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), deleted_at timestamptz
);
create index on work_orders(asset_id, status);
create index on work_orders(planned_start);

create table work_order_tasks (
  id uuid primary key default gen_random_uuid(),
  work_order_id uuid not null references work_orders(id),
  sequence int not null, description text not null,
  done boolean not null default false, done_at timestamptz
);

create table schedules (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  horizon_start timestamptz not null, horizon_end timestamptz not null,
  objective jsonb not null,                   -- weights {downtime_cost, failure_risk, energy_cost}
  solver_status text, solve_ms int, objective_value double precision,
  is_active boolean not null default false
);

create table schedule_items (
  id uuid primary key default gen_random_uuid(),
  schedule_id uuid not null references schedules(id),
  work_order_id uuid not null references work_orders(id),
  technician_id uuid references technicians(id),
  starts_at timestamptz not null, ends_at timestamptz not null,
  risk_before double precision, energy_cost numeric(12,2),
  manually_adjusted boolean not null default false
);
create index on schedule_items(schedule_id);
```

### 7.7 Analytics (M8)

```sql
create table shifts (
  id uuid primary key default gen_random_uuid(),
  plant_id uuid not null references plants(id),
  code text not null, name text not null,
  starts_local time not null, ends_local time not null, days_of_week int[] not null,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), deleted_at timestamptz
);

create table tariffs (
  id uuid primary key default gen_random_uuid(),
  plant_id uuid not null references plants(id),
  name text not null, starts_local time not null, ends_local time not null,
  rate_per_kwh numeric(10,4) not null, days_of_week int[] not null,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), deleted_at timestamptz
);

create table kpi_definitions (
  code text primary key,                      -- oee|availability|performance|quality|mtbf|mttr|energy_per_unit|idle_energy_share|peak_demand
  name text not null, unit text not null,
  formula text not null,                      -- human-readable, shown on hover (FR-PA-06)
  standard_ref text,                          -- 'ISO 22400-2 §6.4'
  version int not null default 1
);

create table kpi_values (
  time timestamptz not null,                  -- period start
  period text not null check (period in ('shift','day','week','month')),
  scope text not null check (scope in ('plant','line','asset')),
  scope_id uuid not null,
  kpi_code text not null references kpi_definitions(code),
  value double precision not null,
  inputs jsonb,                               -- lineage: {run_time_s, planned_time_s, ...}
  formula_version int not null default 1
);
select create_hypertable('kpi_values','time');
create unique index kpi_values_uq on kpi_values(time, period, scope, scope_id, kpi_code);

create table energy_baselines (
  id uuid primary key default gen_random_uuid(),
  scope text not null, scope_id uuid not null,
  period_start timestamptz not null, period_end timestamptz not null,
  intercept_kwh double precision not null, slope_kwh_per_unit double precision not null, r2 double precision,
  created_at timestamptz not null default now()
);
```

### 7.8 Voice (M9)

```sql
create table voice_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id),
  started_at timestamptz not null default now(), ended_at timestamptz,
  channel text not null check (channel in ('voice','chat')),
  device text, lang text not null default 'en',
  context jsonb not null default '{}'         -- {current_asset, last_prediction_id, last_explanation_id}
);

create table voice_turns (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references voice_sessions(id),
  at timestamptz not null default now(),
  transcript text, transcript_confidence double precision, stt_ms int,
  intent text, slots jsonb, intent_confidence double precision, router text check (router in ('rules','llm')), router_ms int,
  tier text check (tier in ('T0','T1','T2','T3')),
  response_text text, tts_ms int, total_ms int,
  snr_db double precision,                    -- for noise studies
  audio_uri text                              -- only if user opted in
);
create index on voice_turns(session_id, at);

create table voice_actions (
  id uuid primary key default gen_random_uuid(),
  turn_id uuid not null references voice_turns(id),
  tool text not null, params jsonb not null, tier text not null,
  readback text,
  status text not null default 'pending' check (status in ('pending','confirmed','cancelled','expired','executed','failed','rejected')),
  validation_errors jsonb,
  confirmed_at timestamptz, second_factor_ok boolean,
  executed_at timestamptz, result jsonb, error text
);
create index on voice_actions(status);

create table intent_examples (
  id uuid primary key default gen_random_uuid(),
  intent text not null, lang text not null, text text not null,
  slots jsonb, noise_variant boolean not null default false, split text not null default 'test'
);
```

### 7.9 Reports (M10) and simulation (M1)

```sql
create table reports (
  id uuid primary key default gen_random_uuid(),
  type text not null check (type in ('machine_health','weekly_maintenance','energy','benchmark','incident')),
  scope text, scope_id uuid, period_start timestamptz, period_end timestamptz,
  format text not null check (format in ('pdf','docx','md')),
  status text not null default 'queued' check (status in ('queued','running','done','failed')),
  file_uri text, summary_text text, summary_audit jsonb,
  requested_by uuid references users(id), requested_via text not null default 'ui',
  created_at timestamptz not null default now(), finished_at timestamptz
);

create table report_schedules (
  id uuid primary key default gen_random_uuid(),
  type text not null, scope text, scope_id uuid, format text not null,
  cron text not null, recipients text[] not null default '{}', enabled boolean not null default true,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table scenarios (
  code text primary key, name text not null, description text, yaml text not null,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table scenario_runs (
  id uuid primary key default gen_random_uuid(),
  scenario_code text references scenarios(code),
  started_at timestamptz not null default now(), ended_at timestamptz,
  time_scale double precision not null default 1, seed int,
  export_uri text
);

create table what_if_runs (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references assets(id),
  requested_by uuid references users(id), requested_via text not null default 'ui',
  params jsonb not null,                      -- {load_pct:80} | {maintenance_at:'...'}
  n_trajectories int not null default 500,
  baseline jsonb, result jsonb,               -- {rul:{p50,p10,p90}, cost, energy_kwh}
  narration text, status text not null default 'queued', started_at timestamptz, finished_at timestamptz
);
```

---

## 8. Module Specifications

Each module lists: purpose and PRD IDs, backend files, frontend files, data owned, detailed features with behaviour, and acceptance checks.

### M0 — Platform Core

**PRD:** NFR-DEP, NFR-SEC, NFR-OBS, NFR-A11Y, NFR-I18N.
**Backend:** `app/core/*`, `app/common/*`, `alembic/`, `workers/celery_app.py`.
**Frontend:** `src/app/*` (AppShell, router, ThemeProvider, AuthProvider, WsProvider), `src/lib/*`, `src/components/*`.

Features:
1. **App factory and lifespan**: creates engine, Ditto client, MQTT client, Valkey; registers module routers; `/health` reports each dependency.
2. **Auth**: Keycloak realm `twinvoice` with roles; frontend uses `keycloak-js` PKCE; API validates JWT via JWKS cache. `require_role` used per endpoint (write endpoints: engineer/admin; work orders: technician+; models: engineer).
3. **Audit**: every create/update/delete/confirm/execute writes `audit_log` in the same transaction.
4. **WebSocket hub**: one connection per browser tab; subscription registry; Valkey subscriber pushes to matching sockets; heartbeat 20 s.
5. **Observability**: structured JSON logs with `request_id`; `/metrics` Prometheus endpoint; Grafana system dashboard provisioned.
6. **i18n**: `i18next` with `en`, `hi`; numbers/dates formatted per locale and plant timezone.
7. **Theme**: Ant Design `ConfigProvider` with the tokens in Section 9; dark default; toggle persisted in `localStorage`.
8. **Shared components**: `StatusTag` (icon + label, never colour-only), `HealthGauge`, `RulBadge` (point + interval + unit), `SensorTile`, `ConfirmReadback` modal, `PageHeader`, `EmptyState`, `KpiTile`, `TimeRangePicker`.

Acceptance: `docker compose up` → all services healthy in ≤ 10 min; login as each role; WS receives heartbeat.

### M1 — Sensor Simulator

**PRD:** FR-SIM-01..09, FR-DT-04 (command handling).
**Files:** `apps/simulator/sim/*`; API proxy `app/modules/simulation/*`; UI `features/simulation/*`.
**Data:** `scenarios`, `scenario_runs`; publishes MQTT; exposes OPC UA (4840) and Modbus (5020).

Features:
1. **Machine library** (FR-SIM-01): five classes deriving from `Machine` with `sensors()`, `step(dt)`, `production()`, `power()`; parameters in YAML. Default fleet: 2 CNC mills, 2 compressors, 3 conveyors, 1 hydraulic press, 2 injection moulders across 2 lines.
2. **Degradation physics** (FR-SIM-02): per component, a `DegradationProcess` (Wiener drift+diffusion, Gamma shape/scale, Paris law `da/dN = C ΔK^m`, Arrhenius factor `exp(-Ea/kT)`, Taylor `VT^n = C`, motor efficiency loss `η = η0 − k·D`). Each process exposes `damage ∈ [0,1]`, `true_rul()`, and `driver` label. Sensor signatures map damage to metrics (vib_rms ∝ damage², temperature ∝ damage, current ∝ 1/η).
3. **Failure modes** (FR-SIM-03): ≥ 4 per type from `failure_modes` table; `inject(mode, sudden|gradual, severity)`; mixed-mode allowed; failure event when damage ≥ 1 → state `DOWN`.
4. **Realism** (FR-SIM-04): Gaussian noise, slow drift, spikes, dropout (missing), stuck sensor, offset, jitter; shift calendar and weekend idle from `shifts`; load follows a production plan.
5. **Scenario control** (FR-SIM-05): YAML scenarios (`demo_day.yaml`, `bearing_failure_cnc01.yaml`, `energy_drift.yaml`, `user_study_A..D.yaml`); REST `inject`, `time-scale` (1×–1000×), `reset` (sets damage=0, logs maintenance event); seeds for reproducibility.
6. **Protocols** (FR-SIM-06): Sparkplug B NBIRTH/DBIRTH with metric metadata (units, types), DDATA at 1 Hz; OPC UA server mirrors the same metrics under `Objects/Plant/Line/Asset/Metric`; Modbus holding registers mapped per asset; optional OpenPLC program for the conveyor.
7. **Waveforms** (FR-SIM-07): 20 kHz, 1 s bursts every 60 s for bearing components; defect frequencies BPFO/BPFI/BSF from geometry; amplitude scales with damage; published as base64 in a separate `twinvoice/wave/{asset}` topic.
8. **Replay** (FR-SIM-08): `replay.py` maps dataset columns to virtual sensors (C-MAPSS 21 sensors → `engine.s01..s21`), emits at configurable time scale.
9. **Export** (FR-SIM-09): Parquet with `time, asset, metrics…, damage, true_rul, driver, failure_mode` → `data/synthetic/`.

UI (`/simulation`): fleet table with damage bars (engineer-only), fault injection form, time-scale slider, scenario picker, export button, live log.

Acceptance: 50 assets × 20 sensors at 1 Hz sustained; export contains monotone `true_rul`; OPC UA browsable with UaExpert.

### M2 — Digital Twin

**PRD:** FR-DT-01..10, FR-SIM-06 write-back.
**Backend:** `modules/assets/*`, `modules/twin/*`, `core/ditto.py`.
**Frontend:** `features/twin/*` (TwinTree, AasViewer, Machine3D, PlantLayout3D, Replay, WhatIf), `three/*`.

Features:
1. **Twin store sync** (FR-DT-01): on asset create, `twin.service.create_thing()` PUTs `things/twinvoice:{code}` with attributes (nameplate) and empty features; ingest PATCHes `features/telemetry/properties`; worker PATCHes `features/prediction`; policies: `technician` read, `engineer` write, `system` write. Twin update ≤ 200 ms measured by ingest timer.
2. **AAS** (FR-DT-02): submodels stored in `aas_submodels`, rendered to AAS JSON v3 via `basyx-python-sdk`; `.aasx` export; import parses AASX from Package Explorer; adapters produce DTDL interface JSON and NGSI-LD entity from the same data.
3. **Hierarchy** (FR-DT-03): `/twin/tree` computes machine health = `min(component_health × weight)`; line health = mean; plant = mean.
4. **Write-back** (FR-DT-04): `POST /twin/{code}/commands` accepts `set_load`, `set_speed`, `maintenance_reset`; tier T3; publishes MQTT command; waits for ack ≤ 5 s; audit.
5. **Fidelity badge** (FR-DT-05): from `assets.fidelity_level`.
6. **3D** (FR-DT-06): `Machine3D` loads glTF, maps `components[].code` to mesh names; material emissive colour from status palette by health band; hover tooltip `RulBadge` + top attribution; alarm pulse via `useFrame`; ≥ 30 fps checked with `r3f-perf` in dev.
7. **Plant layout** (FR-DT-07): `PlantLayout3D` places assets by `assets.position`; click navigates.
8. **Replay** (FR-DT-08): `/twin/{code}/replay` returns state + telemetry_1m + predictions between `from/to`; UI scrubber drives `liveTwinStore` in replay mode; 3D and tiles re-render.
9. **What-if** (FR-DT-09): `POST /twin/{code}/what-if` enqueues Celery task: clone current damage state from simulator (`GET /simulation/state/{asset}`), run `n` trajectories with modified params using the physics package (no MQTT), run RUL model on synthetic windows, return distribution; template narration + LLM paraphrase (audited) stored in `what_if_runs.narration`. ≤ 10 s for 500 trajectories.
10. **Lifecycle** (FR-DT-10): create/clone/retire; retire soft-deletes and sets Ditto policy read-only.

UI: `/twin` (tree + AAS viewer tabs: Nameplate, TechnicalData, OperationalData, MaintenanceHistory, PredictiveMaintenance, raw JSON, DTDL, NGSI-LD), `/twin/3d`, `/twin/replay`, `/twin/what-if` (form + before/after violin chart + narration card + "Speak" button).

### M3 — Ingest, Telemetry and Alarms

**PRD:** FR-MM-03, FR-MM-04, NFR-PERF-01/02, NFR-REL-01.
**Backend:** `app/ingest/*` (consumer), `modules/telemetry/*`.
**Frontend:** `features/alarms/*`, explorer page in `features/monitoring/Explorer.tsx`.

Features:
1. **Consumer**: subscribes `spBv1.0/#` with QoS 1 and persistent session; decodes Sparkplug protobuf; resolves `metric_name` → `sensor_id` via cached map; batches inserts (500 rows or 250 ms) with `COPY`; quality from metric; PATCH Ditto; publish Valkey `live:{asset}`.
2. **Waveform handler**: decodes, computes RMS/kurtosis/crest/defect-band amplitudes, stores row.
3. **State and production**: DBIRTH/DDATA metrics `state`, `good_count`, `reject_count`, `cycle_time_s` routed to their tables; closes previous state event by filling `duration_s`.
4. **Alarm engine**: runs in the consumer per message: threshold rules; adaptive rules keep rolling mean/std per sensor in Valkey (window from params); dedupe: one active alarm per (rule, asset); auto-clear on return-to-normal with 30 s hysteresis; ML alarms raised by worker when `p_fail ≥ rule.min_score`, linked to `prediction_id`.
5. **Queries**: `/telemetry` picks raw / `telemetry_1m` / `telemetry_1h` by range (≤ 6 h raw, ≤ 7 d 1m, else 1h); CSV export streams.
6. **Alarm actions**: ack/assign/comment/shelve with audit; shelve hides until `shelved_until`.

UI: `/explorer` (multi-sensor picker, range picker, ECharts line with prediction and alarm overlays, zoom, export), `/alarms` (table, severity filter, bulk ack, drawer with linked explanation card).

### M4 — Machine Monitoring Dashboard

**PRD:** FR-MM-01, FR-MM-02, FR-MM-05, FR-MM-06, FR-MM-07.
**Frontend:** `features/monitoring/{Fleet.tsx, MachineDetail.tsx, panels/*}`.
**Backend:** composes `/twin/tree`, `/telemetry/latest`, `/predictions/latest`, `/alarms`.

Features:
1. **Fleet overview** (`/`): responsive card grid (or table toggle) per asset: name/type/line, `StatusTag`, `HealthGauge`, `RulBadge`, alarm count, power kW sparkline; filters (line, status, health band); sort; live via WS; role filter for technicians (own line).
2. **Machine detail** (`/machines/:code`): header (status, health, RUL, confidence, fidelity badge, voice button); tabs: **Live** (SensorTile grid with 10-min sparkline and threshold band; 3D panel right), **Prediction** (health trend 24 h, failure probability per mode bar, RUL fan chart with interval history), **Explanation** (M6 card), **Timeline** (state events, alarms, work orders, predictions merged), **AAS**.
3. **Grafana embed**: `/machines/:code/grafana` iframe with provisioned dashboard (var `asset`).
4. **Tablet layout**: ≥ 768 px two-column; < 768 px single column, voice FAB fixed.
5. **Role views**: menu items filtered by role; manager landing = `/analytics/production`.

### M5 — Predictive Maintenance Engine

**PRD:** FR-PM-01..10.
**Library:** `packages/pdm/*`. **Backend:** `modules/pdm/*`, `workers/tasks/{infer,train,benchmark}.py`. **Frontend:** `features/pdm/*`.

Features:
1. **Feature pipeline** (FR-PM-01): `FeatureSpec` (window, stride, stats list, spectral bands, energy features) serialised into `models.feature_set`; `build_features(df, spec)` used identically by trainer, worker and edge. Stats: mean, std, min, max, slope (OLS), kurtosis, RMS, crest; spectral: band energies, envelope defect amplitudes; energy: specific energy kWh/unit, power factor drift, current imbalance; counts: cycles since maintenance.
2. **Anomaly** (FR-PM-02): per asset IsolationForest + ECOD fitted on a healthy baseline window (first 24 h after maintenance reset); River `HalfSpaceTrees` online; ADWIN drift on anomaly score; `health_index = 100 × (1 − clip(score_norm))` with score normalised by baseline quantiles.
3. **Failure classification** (FR-PM-03): LightGBM multiclass (modes + none) on windowed features with horizon `H`; EBM in parallel (M6); logistic baseline; in-fold SMOTE; isotonic calibration on held-out fold.
4. **RUL** (FR-PM-05): PyTorch LSTM (2×64) and TCN on sequences; LightGBM on features; piecewise-linear target cap 125; MAPIE `MapieRegressor` (CV+) → 90 % interval; `lifelines` Weibull AFT as survival alternative; ProgPy fusion when `components.physics_model` set (inverse-variance weighting) (FR-PM-07).
5. **Registry** (FR-PM-04): MLflow file store `mlruns/`; `models` row per run; `promote` demotes previous production model; ONNX export at train time (onnxmltools for GBM, `torch.onnx` for nets); explainer and conformal calibrator pickled alongside.
6. **Inference worker**: Celery beat every 10 s (configurable) per asset: pull last window from `telemetry_1m` (or raw), features, anomaly, failure, RUL, confidence (M6), write `predictions`, PATCH Ditto, publish live, raise ML alarms, enqueue `explain` task.
7. **Cold start** (FR-PM-08): pre-train on `data/synthetic` + public datasets per asset type; per-asset fine-tune when ≥ 6 h of data; `model_metrics` records hours-to-target.
8. **Benchmark runner** (FR-PM-09): `benchmarks/run.py` → C-MAPSS FD001–4 (RMSE, NASA score, coverage), AI4I (AUC, F1), MetroPT-3 (event recall, lead time), leakage-safe unit-level splits, fixed seeds; writes `benchmark_runs` + `benchmarks/results/<date>.md`.
9. **Presentation** (FR-PM-10): `RulBadge` always shows `point (low–high) unit` and urgency colour by `point / horizon`.

UI: `/models` (table: name, version, task, stage, key metrics, actions promote/rollback), `/models/:id` (metrics, calibration reliability diagram, coverage plot, global importance from M6, ONNX download), `/models/benchmarks` (runs and report viewer).

### M6 — Explainable AI

**PRD:** FR-XAI-01..12, FR-EN-04 (energy features as explanatory), FR-RP-04 audit reuse.
**Library:** `packages/xai/*`. **Backend:** `modules/xai/*`, `workers/tasks/explain.py`. **Frontend:** `features/explain/*`.

Features:
1. **Local attribution** (FR-XAI-01): TreeSHAP for LightGBM (exact); DeepSHAP/Integrated Gradients (Captum) for LSTM/TCN; KernelSHAP fallback; output normalised to the `Explanation` schema with human labels from a `feature_labels.yaml` (feature → label, unit, direction words). ≤ 500 ms for tree models (cached by prediction_id).
2. **Global importance** (FR-XAI-02): mean |SHAP|, beeswarm data, PDP for top-8, EBM shape functions; computed at train time and stored under the model artifact.
3. **Temporal attribution** (FR-XAI-03): per-timestep IG for sequence models; concept aggregation into `trend | spike | level_shift` segments.
4. **Glass-box** (FR-XAI-04): EBM trained on the same features; term contributions per prediction; `agreement.shap_vs_ebm_top3_jaccard`; < 0.34 flags "model disagreement" in confidence.
5. **Reason card** (FR-XAI-05): map predicted mode + top-k attributions to `knowledge_base_entries` (by failure mode and matching evidence metrics); card fields symptom/evidence/cause/action/confidence.
6. **Counterfactuals** (FR-XAI-06): DiCE with `features_to_vary` = actionable set (load_pct, speed, coolant_temp, lube_interval); constraints from `feature_labels.yaml` ranges; outcome re-scored with RUL model + conformal; `action_text` from KB.
7. **Narration + audit** (FR-XAI-07): `templates.py` (Appendix B of PRD, en + hi); `llm.py` prompts Qwen3 with the JSON and strict instructions; `audit.py` checks rank (top-3 overlap ≥ 2/3), sign, numbers ±5 %, feature vocabulary, recommendation ⊆ reason card; failure → template; stored in `narrations`/`narration_audits`.
8. **Quality metrics** (FR-XAI-08): Quantus deletion/insertion, PGI, SensitivityMax, sparsity; on synthetic data, `truth_top1_agreement` vs `driver`; window Jaccard stability; computed at train time and nightly.
9. **Feedback** (FR-XAI-09): `POST /explanations/{id}/feedback` from UI buttons, voice `give_feedback`, chat; disagree with `suspect_sensor_id` sets sensor quality flag that lowers confidence for 1 h and notifies engineer.
10. **Calibration** (FR-XAI-10): reliability diagram + ECE per model.
11. **Confidence** (FR-XAI-11): `confidence.py` combines interval width ratio (`(high−low)/point`), model agreement, sensor quality (stuck/missing in window), drift/OOD → label + reasons; explanation text via template.
12. **Drift/OOD** (FR-XAI-12): ADWIN on features, KS test vs training distribution, OOD = Mahalanobis distance to training manifold; banner in UI when flagged.

UI: `ExplanationCard` (waterfall of top-8 attributions with direction icons, EBM second-opinion chips, confidence popover with reasons, reason card, counterfactual table, Agree/Disagree/Unsure with reason input, "Speak" button), `/explain/quality` (per model: metrics table, stability chart, truth agreement, narration audit pass rate).

### M7 — Maintenance Scheduling

**PRD:** FR-MS-01..06, FR-EN-05.
**Backend:** `modules/maintenance/*` (`optimiser.py` CP-SAT). **Frontend:** `features/maintenance/*`.

Features:
1. **Work orders** (FR-MS-01): CRUD; auto-creation by worker when calibrated `p_fail ≥ threshold` (per asset type, default 0.6) and no open order for that mode; explanation attached; `created_via`.
2. **Optimiser** (FR-MS-02): CP-SAT model: variables start time per order (15-min slots), technician assignment; constraints: availability, skills, one order per line at a time, order within horizon; objective = Σ (downtime_cost × duration) + Σ risk_before_slot × failure_cost + Σ energy_cost(slot tariff) (FR-EN-05); risk from RUL interval via survival function of a Weibull fitted to (low, point, high); solve ≤ 10 s; re-run on material RUL change (> 20 %).
3. **Gantt** (FR-MS-03): ECharts custom series; drag updates `schedule_items` (`manually_adjusted`), re-scores risk and cost, shows conflicts.
4. **Risk explanation** (FR-MS-04): `/work-orders/{id}/risk` returns P(failure before slot) and delta for ±24 h.
5. **Closure feedback** (FR-MS-05): on close, publish `maintenance_reset` command (T3, auto-approved when actor is technician closing own order), simulator resets damage; worker compares pre-order prediction to outcome and sets `prediction_was_correct`.
6. **Export** (FR-MS-06): CSV/JSON; B2MML-like XML template.

UI: `/maintenance` (orders table + drawer; create form with asset picker, failure mode, tasks, parts), `/maintenance/schedule` (Gantt, "Optimise" button with weights popover, risk overlay).

### M8 — Production and Energy Analytics

**PRD:** FR-PA-01..06, FR-EN-01..03, FR-EN-06.
**Backend:** `modules/analytics/*` (`oee.py`, `energy.py`, `kpi_rollup` task). **Frontend:** `features/analytics/*`.

Features:
1. **OEE rollup** (FR-PA-01): Celery beat at shift end + hourly incremental: availability = run_time / planned_time (from `asset_state_events` and `shifts`), performance = ideal_cycle_time × total_count / run_time, quality = good / total; stored per scope/period with `inputs` lineage.
2. **Downtime Pareto** (FR-PA-02): aggregate `asset_state_events` where state DOWN/IDLE by `cause_code`.
3. **Reliability KPIs** (FR-PA-03): MTBF/MTTR/MTTF from DOWN events with cause `breakdown` and work order actual times.
4. **Production vs plan** (FR-PA-04): planned from scenario/production plan; actual from counts; cycle-time histogram.
5. **KPI definitions** (FR-PA-06): `kpi_definitions` served to UI; hover shows formula + inputs.
6. **Energy** (FR-EN-01): power/energy per asset/line/plant; cost from `tariffs`; CO2 from `plants.grid_emission_factor`.
7. **Intensity and baseline** (FR-EN-02): kWh/unit, kWh/run-hour, idle share, peak demand; baseline regression per scope stored in `energy_baselines`.
8. **Energy anomalies** (FR-EN-03): residual vs baseline > 3σ → alarm rule kind `energy_intensity`; correlation with health shown.
9. **Report data** (FR-EN-06): service methods reused by M10.
10. Process mining (FR-PA-05) deferred to v2 (PM4Py, AGPL, optional).

UI: `/analytics/production` (KPI tiles OEE/A/P/Q with trend, downtime Pareto, MTBF/MTTR table, production vs plan), `/analytics/energy` (power now, intensity trend vs baseline, top-5 consumers, anomalies table, cost/CO2 tiles).

### M9 — VoiceNav

**PRD:** FR-VN-01..12, FR-NL-01..06.
**Service:** `apps/voice/*`. **Backend:** `modules/voice/*` (tool execution + tiers). **Frontend:** `features/voice/*` (VoiceFab, VoiceConsole, ConfirmReadback, TranscriptDrawer, ChatPanel).

Features:
1. **STT** (FR-VN-01): faster-whisper `small` INT8 (CPU) or `large-v3-turbo` if GPU; Silero VAD; `initial_prompt` built from asset/component names and units; `hotwords` where supported; post-correction via rapidfuzz against asset codes/names (`fuzzy_assets.py`, threshold 85).
2. **Activation** (FR-VN-02, FR-VN-11): browser push-to-talk (FAB hold or spacebar) streams PCM over WS; optional wake word runs in the voice service on a continuous stream from the tablet when hands-free session is on; self-trained `hey_twin.onnx`.
3. **TTS** (FR-VN-03): Kokoro via sherpa-onnx, voice `af_heart` (en) / multilingual fallback for hi; streamed in sentence chunks; `repeat`, `slower` control intents.
4. **Dialogue state** (FR-VN-05): `voice_sessions.context` holds current asset, last prediction/explanation, last list; referent resolution for "it/that/why"; 2-min inactivity expiry.
5. **Router** (FR-NL-02): stage 1 spaCy `Matcher` patterns from `intents.yaml` (top-30 phrasings, en/hi/hinglish) with slot regexes → confidence 0.95; stage 2 Ollama chat with tools (JSON schema per intent) `temperature 0`, `format: json`; LLM returns tool name + args only; no free text answers.
6. **Tiers and confirmation** (FR-VN-07): `tiers.py`: T0 execute; T1 execute (results hypothetical); T2 read-back → wait `confirm|cancel` 10 s → validate params against API (`asset exists`, `date future`, `technician available`) → execute; T3 additionally requires second factor (on-screen tap + PIN from Keycloak attribute) and is disabled unless `TV_ALLOW_T3=true`. Every step logged to `voice_actions`.
7. **Grounding** (FR-NL-03): responses composed from tool results via templates (`narrate.py`); LLM paraphrase optional and audited (reuses M6 audit for explanation-type responses; numeric audit for KPI responses); citations `{asset, time, model_version}` attached.
8. **Barge-in and errors** (FR-VN-06): client stops playback on PTT; transcript confidence < 0.6 → "Did you mean …?" with top-2 fuzzy matches; unknown intent → help.
9. **Text parity** (FR-NL-04): `POST /chat` uses the same router and tiers; confirmation via button.
10. **Navigation** (FR-NL-05): `navigate_dashboard` emits a WS `voice` event consumed by `uiStore` → router push.
11. **Noise** (FR-VN-09): `tests/noise_eval.py` mixes MIMII/DCASE noise at 55/65/75 dB SNR into the 500-utterance suite; reports WER and intent F1; augmentation used when fine-tuning the rules/LLM examples.
12. **Multilingual** (FR-VN-10): `set_lang` or auto-detect from Whisper; responses in same language; hi templates.
13. **Edge** (FR-VN-12): `apps/voice` runs with `whisper.cpp` backend flag on Raspberry Pi 5.
14. **Intent suite** (FR-NL-06): `intent_examples` seeded from `intents.yaml`; pytest asserts ≥ 92 % accuracy.

UI: `VoiceFab` (56 px, bottom-right, states idle/listening ring/thinking/speaking), `VoiceConsole` drawer (live transcript, intent chip with tier badge, response with citations, feedback buttons), `ConfirmReadback` modal (read-back text, countdown, Confirm/Cancel, PIN field for T3), `/voice` page (session history, help list of commands, language switch), `ChatPanel` (same components, typed input).

### M10 — Reports

**PRD:** FR-RP-01..06.
**Backend:** `modules/reports/*`, `workers/tasks/report.py`, `reports/templates/*.html.j2`. **Frontend:** `features/reports/*`.

Features:
1. Types: machine_health, weekly_maintenance (includes prediction accuracy from `work_orders.prediction_was_correct`), energy, benchmark, incident (timeline ± 48 h around a failure with explanations and actions).
2. Rendering: Jinja2 → HTML (print CSS using the light theme) → WeasyPrint PDF; DOCX via python-docx from the same data; MD for benchmark; charts by matplotlib with the Section 9 palette.
3. Triggers: UI/voice (`generate_report`, T2), Celery beat from `report_schedules`, events (failure, order closure).
4. Summary: 150-word LLM summary from KPI JSON; numeric audit (every number appears in JSON); fallback template summary.
5. Spoken summary via voice when requested by voice.
6. Archive: files under `data/reports/{yyyy}/{mm}/`; list filtered by role.

UI: `/reports` (list, filters, generate modal, schedule table, PDF preview drawer).

### M11 — Edge Runner

**PRD:** FR-EDGE-01..04.
**Files:** `apps/edge/*`.

Features:
1. Export at train time (FR-EDGE-01); parity test asserts ONNX vs native outputs ≤ 1e-4.
2. Runner (FR-EDGE-02): subscribes MQTT for its asset, computes features with `packages/pdm/features`, ONNX inference, TreeSHAP via `shap` on the LightGBM booster file, publishes `twinvoice/pred/{asset}`; logs inference and explanation latency and energy (via `powermetrics`/RAPL where available) to a local CSV.
3. Store-and-forward (FR-EDGE-03): SQLite queue; replays on reconnect.
4. TinyML (FR-EDGE-04): optional CWRU classifier notebook, LiteRT micro export, Renode simulation script.

---

## 9. UI/UX Specification

### 9.1 Design principles

- **Glanceable first.** A technician must read status, health and RUL of a machine in under two seconds from two metres away on a tablet. Large numbers, high contrast, status always icon + label.
- **Dark by default.** Shop floors have glare and long shifts; dark theme reduces fatigue. Light theme is complete (reports, offices).
- **Numbers carry uncertainty.** RUL is never a bare number; probabilities show calibration; explanations show confidence.
- **Voice is a first-class input**, not an add-on: the voice button is always present; every voice response is also visible as text.
- **One visual system for app and charts.** Chart palette, status colours and UI tokens come from the same set.

### 9.2 Colour system

**UI tokens (Ant Design `ConfigProvider` → `theme.token`)**

| Token | Dark | Light |
|---|---|---|
| Page plane (`colorBgLayout`) | `#0d1117` | `#f7f8fa` |
| Surface (`colorBgContainer`) | `#161b22` | `#ffffff` |
| Raised / hover (`colorBgElevated`) | `#1f2630` | `#ffffff` |
| Border (`colorBorder`) | `rgba(255,255,255,0.10)` | `rgba(11,11,11,0.10)` |
| Primary ink (`colorText`) | `#ffffff` | `#0b0b0b` |
| Secondary ink (`colorTextSecondary`) | `#c3c2b7` | `#52514e` |
| Muted (`colorTextTertiary`) | `#898781` | `#898781` |
| Gridline | `#2c2c2a` | `#e1e0d9` |
| Brand primary (`colorPrimary`) | `#3987e5` | `#2a78d6` |
| Primary hover | `#5598e7` | `#256abf` |
| Success | `#0ca30c` | `#006300` (text) / `#0ca30c` (mark) |
| Warning | `#fab219` | `#fab219` |
| Error | `#d03b3b` | `#d03b3b` |
| Focus ring | `#3987e5` at 40 % | `#2a78d6` at 40 % |

**Status palette (fixed, never used for series; always with icon + label)**

| State | Hex | Icon | Used for |
|---|---|---|---|
| good | `#0ca30c` | check-circle | health 80–100, RUNNING, alarms cleared |
| warning | `#fab219` | exclamation-circle | health 60–79, IDLE, warning alarms |
| serious | `#ec835a` | warning | health 40–59, MAINTENANCE, serious alarms |
| critical | `#d03b3b` | close-circle | health < 40, DOWN, critical alarms |
| neutral | `#898781` | minus-circle | UNKNOWN, shelved |

**Chart categorical palette (validated: all checks pass on `#161b22` dark and `#f7f8fa` light; light slots 3, 4, 5 are below 3:1 so charts using them ship direct labels or a table view)**

| Slot | Hue | Dark | Light | Typical assignment |
|---|---|---|---|---|
| 1 | blue | `#3987e5` | `#2a78d6` | primary series, RUL point, first sensor |
| 2 | orange | `#d95926` | `#eb6834` | second sensor / comparison |
| 3 | aqua | `#199e70` | `#1baf7a` | third sensor |
| 4 | yellow | `#c98500` | `#eda100` | fourth |
| 5 | magenta | `#d55181` | `#e87ba4` | fifth |
| 6 | green | `#008300` | `#008300` | sixth |
| 7 | violet | `#9085e9` | `#4a3aa7` | seventh |
| 8 | red | `#e66767` | `#e34948` | eighth |

Rules: assign in fixed order, never cycled; > 8 series → "Other" or small multiples; scatter/heatmap use only slots 1–3; colour follows the entity (a sensor keeps its slot when others are toggled).

**Sequential ramp (blue, for SHAP magnitude heatmaps, temporal attribution)**: `#cde2fb → #9ec5f4 → #6da7ec → #3987e5 → #2a78d6 → #1c5cab → #0d366b`.
**Diverging (SHAP contribution sign, energy residual)**: blue `#2a78d6` ↔ grey mid (`#383835` dark / `#f0efec` light) ↔ red `#e34948`.
**RUL fan chart**: point line slot 1; 90 % band slot 1 at 20 % alpha; horizon threshold line muted dashed.

### 9.3 Typography and numerals

- Font: **Inter** (Google Fonts, OFL) with fallback `system-ui, "Segoe UI", sans-serif`. No display or serif faces.
- Scale: 12 (caption), 14 (body), 16 (emphasis), 20 (card title), 28 (KPI), 40 (hero number on machine header).
- `font-variant-numeric: tabular-nums` on tables, axis ticks, KPI tiles; proportional elsewhere.
- Units always adjacent to the number in secondary ink (`38 cycles`, `2.31 mm/s`).

### 9.4 Spacing, shape, motion

- 8 px spacing scale (4, 8, 12, 16, 24, 32, 48). Card radius 12 px, control radius 8 px, tag radius 999 px.
- Elevation by border and background step, not shadow (dark theme); light theme adds `0 1px 2px rgba(0,0,0,.06)`.
- Motion: 150 ms ease for hovers, 250 ms for drawers; live tile value changes flash background at 8 % primary for 400 ms; alarm pulse 1.2 s loop; all animations disabled under `prefers-reduced-motion`.

### 9.5 Layout shell

```
┌────────────────────────────────────────────────────────────────────────┐
│ TopBar: ☰ | TwinVoice | Plant ▾ Line ▾ | 🔍 search (⌘K) | 🌐 en | ☾ | 👤 │
├────────┬───────────────────────────────────────────────────────────────┤
│ Nav    │ PageHeader (title, breadcrumb, actions, time-range)            │
│ Fleet  │                                                               │
│ Machines│  content grid (12 col, 24 px gutter, max 1600 px)            │
│ Explorer│                                                               │
│ Alarms │                                                               │
│ Twin ▸ │                                                               │
│ Models │                                                               │
│ Maint ▸│                                                               │
│ Analytics▸                                                             │
│ Voice  │                                                          [🎤] │
│ Reports│                                                   VoiceFab    │
│ Sim    │                                                               │
└────────┴───────────────────────────────────────────────────────────────┘
```

Breakpoints: ≥ 1200 px full nav; 768–1199 collapsed icon nav; < 768 bottom tab bar (Fleet, Alarms, Voice, Maintenance) and VoiceFab.

### 9.6 Component specifications

| Component | Spec |
|---|---|
| `StatusTag` | Ant `Tag` with icon + text; background = status colour at 16 %, text = status colour (dark) or darkened variant (light); never colour-only |
| `HealthGauge` | 72 px ring, value in 28 px tabular; ring colour by band; tooltip shows anomaly score and baseline date |
| `RulBadge` | `38 cycles` bold, `(29–47, 90 %)` secondary, urgency colour by point/horizon ratio; tooltip: model version, coverage, physics/fused values |
| `SensorTile` | Name, value + unit (20 px), 10-min sparkline (slot colour), threshold band shading, quality dot; click → explorer with sensor preselected |
| `KpiTile` | Title, value (28 px), delta vs previous period with arrow + `Δ good` text colour, formula on hover (info icon) |
| `ExplanationCard` | Waterfall bar chart (contributions, diverging colours), attribution rows with direction icon and feature label, EBM chips, confidence popover, reason card, counterfactual table, feedback buttons, Speak button |
| `ConfirmReadback` | Modal, read-back text in 20 px, 10 s countdown ring, Confirm (primary) / Cancel; T3 shows PIN input; keyboard: Enter confirm, Esc cancel |
| `VoiceFab` | 56 px circle, mic icon; states: idle (primary), listening (pulsing ring + level meter), thinking (spinner), speaking (waveform); long-press or hold-space to talk |
| `TimeRangePicker` | Presets (last 1 h, 8 h, 24 h, 7 d, 30 d, shift, custom); drives all charts on the page |
| `EmptyState` | Illustration-free: icon, one sentence, primary action |
| `Chart` wrapper | ECharts with theme registration (`echartsTheme.ts` generated from tokens), crosshair tooltip on lines, per-mark tooltip on bars, legend for ≥ 2 series, direct labels ≤ 4 series, table-view toggle |

### 9.7 Screen inventory

| Route | Module | Layout and key elements | States |
|---|---|---|---|
| `/` Fleet | M4 | Filter row (line, status, health band, search); card grid 4/3/2/1 columns; card = name, type, `StatusTag`, `HealthGauge`, `RulBadge`, alarms badge, power sparkline; table toggle | loading skeleton cards, empty "No machines match", live updates |
| `/machines/:code` | M4 | Header (name, status, health, RUL, confidence, fidelity, actions: Create WO, What-if, Speak); tabs Live / Prediction / Explanation / Timeline / AAS; right rail 3D panel (collapsible) | stale banner when last telemetry > 60 s; drift banner |
| `/explorer` | M3 | Left: sensor tree with checkboxes (by asset/component); top: time range, aggregation, overlays (predictions, alarms, work orders); main: ECharts multi-line with shared crosshair; export | max 8 series, prompt to facet beyond |
| `/alarms` | M3 | Severity summary tiles; table (time, asset, severity tag, title, value/threshold, status, assignee); row drawer with actions and linked explanation | bulk ack; shelved section collapsed |
| `/twin` | M2 | Tree (plant → line → asset → component with health dots); right: AAS tabs; export AASX/DTDL/NGSI-LD | |
| `/twin/3d` | M2 | Full-height canvas; plant layout; asset labels; click → focus; legend of status colours | fps counter in dev |
| `/twin/replay` | M2 | Timeline scrubber (with alarm/failure markers), speed control, 3D + tiles in replay mode | |
| `/twin/what-if` | M2 | Left form (asset, parameter, value, n); right: before/after RUL violin, cost/energy delta tiles, narration card, Speak | queued/running progress |
| `/models` | M5 | Table + stage tags; promote/rollback with confirm | |
| `/models/:id` | M5/M6 | Metrics table, reliability diagram, coverage, global importance beeswarm, PDP, quality metrics, ONNX download | |
| `/explain/quality` | M6 | Model picker; faithfulness/stability/truth-agreement charts; narration audit pass rate over time; recent failed audits table | |
| `/maintenance` | M7 | Orders table (number, asset, type, priority, status, planned, technician, risk); drawer; create modal | |
| `/maintenance/schedule` | M7 | Gantt (rows = technicians or lines), risk overlay, Optimise button with weight sliders, conflicts panel | |
| `/analytics/production` | M8 | KPI tiles (OEE, A, P, Q, MTBF, MTTR); OEE trend; downtime Pareto; production vs plan; cycle-time histogram | |
| `/analytics/energy` | M8 | Tiles (power now, kWh today, cost, CO2); intensity vs baseline line with residual band; top-5 bar; anomalies table | |
| `/voice` | M9 | Session list; transcript timeline; command cheat-sheet; language switch; hands-free toggle | |
| `/reports` | M10 | List with type/format/status; generate modal; schedules table; preview drawer | |
| `/simulation` | M1 | Fleet damage table; inject fault form; time scale; scenario picker; export; log | engineer/admin only |

### 9.8 Voice UX flow

1. Hold FAB (or space) → earcon "listen" → ring pulses with level meter → partial transcript appears in a toast.
2. Release → earcon "processing" → intent chip appears (`create_work_order · T2`).
3. T0/T1: response text card + TTS; citations expandable.
4. T2: `ConfirmReadback` opens, TTS reads it, 10 s countdown; "confirm" spoken or clicked → executes → success toast with ID, TTS confirms. Cancel/expire → TTS "Cancelled".
5. T3: as T2 plus PIN; disabled by default.
6. Errors: low STT confidence → "Did you mean CNC three or CNC two?" chips; unknown intent → help card.
7. Feedback: after an explanation is spoken, the card shows Agree/Disagree; voice "that's wrong because …" maps to `give_feedback`.

### 9.9 Accessibility

WCAG 2.1 AA contrast for text; status icon + label; focus visible; full keyboard paths for all voice actions; ARIA live region announces new critical alarms; `prefers-reduced-motion` honoured; chart table-view toggle; hit targets ≥ 44 px on tablet.

---

## 10. Development Workflow, CI and Quality Gates

### 10.1 Local loop

```
make up            # docker compose up -d (infra + api + web dev server)
make seed          # plants/lines/assets/sensors/failure modes/KB/tariffs/shifts/users
make sim SCENARIO=demo_day
make train         # baseline models on synthetic + public data → registry (production stage)
make bench         # benchmarks/run.py → results md
make test          # pytest (api, packages, simulator, voice suite), vitest, playwright smoke
make lint          # ruff, mypy, eslint, tsc, pip-licenses gate
```

Python managed with `uv` (workspace: apps/api, apps/simulator, apps/voice, apps/edge, packages/pdm, packages/xai). Frontend with `pnpm`. Types generated: `pnpm gen:api` runs `openapi-typescript` against `http://localhost:8000/openapi.json`.

### 10.2 Branching and commits

`main` protected; feature branches `feat/m5-rul-conformal`; conventional commits (`feat(pdm): add MAPIE intervals`); PR template with checklist (tests, migration reversible, FR-IDs covered, licence scan clean). No force-push; no direct pushes to main.

### 10.3 CI (GitHub Actions, free for public repo)

Jobs: `lint` (ruff, mypy, eslint, tsc), `licences` (pip-licenses + license-checker against allow-list: MIT, BSD, Apache-2.0, PSF, MPL-2.0, EPL-2.0, LGPL (dynamic), NOSA; deny GPL/AGPL in `apps/api` and `packages/*` unless listed as isolated service), `test-python` (Postgres+Timescale service container, migrations up/down, pytest), `test-web` (vitest), `e2e` (compose up, Playwright smoke: login, fleet loads, chat "how is cnc-01"), `intent-suite` (≥ 92 % gate), `benchmark-smoke` (FD001 subset, RMSE threshold).

### 10.4 Testing strategy

| Layer | Tests |
|---|---|
| packages/pdm | feature determinism, target capping, conformal coverage on synthetic, ONNX parity |
| packages/xai | attribution schema, audit rules (crafted good/bad narratives), truth agreement on synthetic |
| api | service tests per module with DB; tier state machine; alarm dedupe/hysteresis; OEE formulas against hand-computed fixtures |
| simulator | monotone damage, true_rul decreasing, Sparkplug encode/decode round trip |
| voice | 500-utterance suite; noise sweep; readback formatting; expiry |
| web | component tests (StatusTag, RulBadge, ConfirmReadback keyboard), Playwright flows |

---

## 11. Build Phases and Exit Criteria

| Phase | Weeks | Modules | Exit criteria |
|---|---|---|---|
| P0 Foundation | 1–2 | M0, infra | Compose up; Keycloak login; migrations; seed; WS heartbeat; CI green |
| P1 Simulate + Twin + Ingest | 3–6 | M1, M2 (1–5), M3, M4 (fleet, live tab) | 10 simulated machines live on fleet page; Ditto twins updating; alarms firing; explorer works |
| P2 Predict | 7–10 | M5 | Predictions with intervals on machine page; benchmark FD001 RMSE ≤ 13; registry + promote |
| P3 Explain | 11–13 | M6 | ExplanationCard live; narration audit pass rate reported; feedback stored; quality page |
| P4 Voice | 14–17 | M9 | "How is compressor two?" → spoken answer; T2 work order via voice with read-back; intent suite ≥ 92 % |
| P5 Maintain + Analyse | 18–20 | M7, M8 | CP-SAT schedule + Gantt; OEE/energy pages with lineage; energy anomalies |
| P6 Report + 3D + What-if | 21–23 | M10, M2 (6–9) | PDF weekly report by voice; 3D machine with overlays ≥ 30 fps; what-if narrated ≤ 10 s |
| P7 Edge + Study | 24–30 | M11, benchmarks, user_study | Edge parity + latency table; user study run; papers 1–2 drafted |

---

## 12. Requirement Traceability

| PRD ID range | Module | Notes |
|---|---|---|
| FR-MM-01, 02, 05, 06, 07 | M4 | |
| FR-MM-03, 04 | M3 | explorer and alarms |
| FR-PA-01..04, 06 | M8 | FR-PA-05 (process mining) deferred to v2 |
| FR-EN-01..03, 06 | M8 | |
| FR-EN-04 | M5 + M6 | energy features in pipeline; explained by SHAP |
| FR-EN-05 | M7 | tariff-aware objective |
| FR-DT-01..10 | M2 | |
| FR-SIM-01..09 | M1 | |
| FR-PM-01..10 | M5 | |
| FR-XAI-01..12 | M6 | |
| FR-MS-01..06 | M7 | |
| FR-VN-01..12 | M9 | FR-VN-12 optional edge voice |
| FR-NL-01..06 | M9 | |
| FR-RP-01..06 | M10 | |
| FR-EDGE-01..04 | M11 | FR-EDGE-04 optional |
| NFR-* | M0 + CI | licence gate, observability, accessibility, i18n |

Every PRD functional requirement maps to exactly one primary module; two are explicitly deferred (FR-PA-05) or optional (FR-EDGE-04, FR-VN-12) as marked in the PRD priorities.
