# Modules M3 + M4 + M5 Implementation Walkthrough

We have completed the full implementation of **M3 (Telemetry Data Platform & Alarm Engine)**, **M4 (Asset Health Monitoring Platform)**, and **M5 (Predictive Maintenance & Model Registry)** according to the project specifications in `docs/ARCHITECTURE.md`.

---

## Architecture Summary

```
               ┌────────────────────────────────────────────────────────┐
               │                  MQTT / Broker                         │
               └──────────────────────────┬─────────────────────────────┘
                                          │
                                          ▼
                         ┌─────────────────────────────────┐
                         │   Telemetry Ingest Consumer     │
                         │   (app/ingest/consumer.py)      │
                         └────────────────┬────────────────┘
                                          │
                  ┌───────────────────────┼───────────────────────┐
                  ▼                       ▼                       ▼
      ┌──────────────────────┐  ┌───────────────────┐   ┌────────────────────┐
      │ TimescaleDB Hypertab │  │   Alarm Engine    │   │  Live WebSocket    │
      │ (telemetry & pred)   │  │ (alarm_engine.py) │   │  Broadcaster       │
      └──────────────────────┘  └───────────────────┘   └─────────┬──────────┘
                                                                  │
                                                                  ▼
                                                        ┌────────────────────┐
                                                        │ Zustand Live Store │
                                                        │ (liveTwinStore.ts) │
                                                        └────────────────────┘
```

---

## 1. Database Migrations (TimescaleDB & PostgreSQL)

- **`0004_telemetry.py`**:
  - `telemetry` hypertable (`timestamp`, `asset_id`, `sensor_code`, `value`, `quality`) with composite chunk index on `(asset_id, sensor_code, timestamp DESC)`
  - Continuous aggregates: `telemetry_1m_avg`, `telemetry_1h_avg`
  - `alarm_rules` & `alarms` tables with full lifecycle (`ACTIVE`, `ACKNOWLEDGED`, `SHELVED`, `CLEARED`)
  - `state_events` table tracking machine status transitions (`RUNNING`, `IDLE`, `FAULT`, `OFFLINE`, `MAINTENANCE`)
  - `energy_rollup_1h` & `production_counter_1h` tables
- **`0005_pdm.py`**:
  - `pdm_models` registry (`model_id`, `version`, `task`, `algorithm`, `stage`, `artifact_uri`, `params`, `metrics`)
  - `pdm_model_metrics` table for evaluation metrics tracking
  - `pdm_predictions` hypertable (`timestamp`, `asset_id`, `model_id`, `anomaly_score`, `health_index`, `failure_prob_*`, `rul_point`, `rul_ci_lower`, `rul_ci_upper`)

---

## 2. Backend Modules & Ingestion Engine

### M3 Telemetry & Alarms (`app/modules/telemetry/`)
- `repository.py` & `service.py`: High-performance batch insertion into TimescaleDB hypertable, range queries, latest sensor state retrieval, alarm rule management, and alarm acknowledgment/shelving.
- `router.py`: Exposes `/api/v1/telemetry`, `/api/v1/telemetry/latest`, `/api/v1/alarms`, `/api/v1/alarms/rules`.

### Ingest Engine (`app/ingest/`)
- `consumer.py`: Asynchronous MQTT payload processor parsing sensor payloads, updating live memory state, routing to alarm engine, and broadcasting via WebSocket.
- `alarm_engine.py`: Real-time threshold evaluation (`GT`, `LT`, `EQ`, `NEQ`) with hysteresis and deadband support.

### M5 Predictive Maintenance (`app/modules/pdm/` & `app/workers/`)
- `repository.py` & `service.py`: PDM model management, deployment stage promotion (`candidate` → `staging` → `production`), prediction query engine.
- `workers/tasks/infer.py` & `train.py`: Celery tasks for scheduled batch inference and automated model retraining/benchmarking.

---

## 3. Dedicated `packages/pdm` ML Library

Located at `packages/pdm/`:
- **`pdm.features`**: Sliding window feature extractors (mean, std, min, max, RMS, kurtosis, skewness, peak factor, FFT spectral centroid, peak frequency).
- **`pdm.anomaly`**: Isolation Forest anomaly scoring with rolling baseline calibration and non-linear `health_index` mapping (\(0 - 100\)).
- **`pdm.failure`**: LightGBM multi-class failure mode classifier (`normal`, `bearing_wear`, `impeller_damage`, `overheating`, `electrical_fault`) with Isotonic Regression probability calibration.
- **`pdm.rul`**: LightGBM RUL regressor with **MAPIE (Conformal Prediction)** interval estimation (\(90\%\) prediction intervals).
- **`pdm.registry`**: MLflow integration for model metadata and artifact tracking.
- **`pdm.datasets`**: Synthetic data generator and NASA C-MAPSS dataset loader.

---

## 4. Frontend Web App (React + Ant Design + Zustand + ECharts)

### Live State Management
- `liveTwinStore.ts`: High-performance Zustand store maintaining real-time telemetry, alarm badges, and asset health/RUL updates received via WebSocket.

### Shared UI Components
- **`HealthGauge.tsx`**: 72px SVG ring gauge displaying asset health (\(0-100\)) with color-coded health bands (Normal, Warning, Critical) and smooth SVG stroke animations.
- **`RulBadge.tsx`**: Visual badge with point estimate, lower/upper confidence bounds, and urgency highlight.
- **`SensorTile.tsx`**: Live sensor metric card featuring large value/unit display, sensor quality dot, and inline SVG sparklines.
- **`KpiTile.tsx`**: Industrial KPI indicator card with value formatting, delta indicators, and calculation formula tooltips.
- **`TimeRangePicker.tsx`**: Time range selector supporting quick presets (`1h`, `8h`, `24h`, `7d`, `30d`) and custom range picking.

### Main Feature Pages
- **Fleet Overview (`/`)**: Responsive card grid showing health ring gauges, RUL badges, current power usage, active alarms, and machine status filters.
- **Machine Detail (`/machines/:code`)**: Comprehensive machine view featuring machine header, live sensor grid, prediction summary, and timeline history.
- **Alarms Management (`/alarms`)**: Active alarm dashboard with severity summary counters, filterable alarm table with row selection, drawer details, and bulk acknowledge/shelve controls.
- **Telemetry Explorer (`/explorer`)**: Multi-sensor historical telemetry visualizer with time range selectors.
- **Model Registry (`/models` & `/models/:id`)**: PDM model registry showing model metrics, promotion flow (`staging` → `production`), parameter summary, and feature importance.

---

## 5. Verification & Testing

- Unit test added for telemetry alarm engine: `apps/api/tests/test_telemetry.py`
- Unit test added for PDM pipeline components: `packages/pdm/tests/test_pdm_pipeline.py`
