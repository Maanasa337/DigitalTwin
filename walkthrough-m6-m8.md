# Modules M6 + M7 + M8 Implementation Walkthrough

Full implementation of **M6 (Explainable AI)**, **M7 (Maintenance Scheduling)** and **M8 (Production & Energy Analytics)**, per `docs/ARCHITECTURE.md` §7.5–7.7 and §M6–M8.

---

## Architecture Summary

```
      Prediction written (M5 infer worker)
                    │
                    ├──────────────► explain task (M6) ──► explanations
                    │                    │                 counterfactuals
                    │                    │                 narrations + audits
                    │                    ▼
                    │              ExplanationCard  ◄── operator feedback ──► sensor quality flag
                    │
                    └──────────────► raise_predictive_orders (M7)
                                         │
                                    work_orders ──► CP-SAT optimiser ──► schedules
                                         │              ▲                    │
                                    close order         │              schedule_items
                                         │         tariffs (M8)              │
                              maintenance_reset ─► simulator            Gantt + conflicts
                                         │
                                         ▼
                        asset_state_events + production_counts + energy_readings
                                         │
                                    KPI rollup (M8) ──► kpi_values ──► /analytics pages
                                         │
                                  energy_baselines ──► anomalies (residual > 3σ)
```

---

## 1. Database Migrations

- **`0006_xai.py`** — `knowledge_base_entries` (specified in §7.2 but never built; M6 is its only reader), `explanations` (unique on `prediction_id` so a retried task cannot duplicate), `counterfactuals`, `narrations`, `narration_audits`, `explanation_feedback`, `explanation_quality_metrics`. Adds `sensors.quality_flag` / `quality_flag_until` for FR-XAI-09.
- **`0007_maintenance.py`** — `technicians`, `technician_availability`, `work_orders` (partial-unique index enforces *one open auto-raised order per asset and failure mode*, so two concurrent inference workers cannot both raise it), `work_order_tasks`, `schedules` (partial-unique index on `is_active` allows exactly one active plan), `schedule_items`.
- **`0008_analytics.py`** — `shifts`, `tariffs`, `kpi_definitions` (seeded with the nine ISO 22400 / ISO 50001 definitions the UI shows on hover), `kpi_values` hypertable with an upsert key so re-running a rollup for an open period refines rather than duplicates, `energy_baselines`.

`explanations.prediction_id` carries no FK: `predictions` is a Timescale hypertable and inbound FKs to one are not permitted.

---

## 2. `packages/xai` — the M6 library

| Module | Responsibility |
|---|---|
| `labels.py` | `feature_labels.yaml` → label, unit, actionable range. A YAML-named feature wins over suffix stripping, so `spindle.vib_rms` is a sensor, not the RMS of a `spindle.vib`. |
| `attribution.py` | TreeSHAP / KernelSHAP / integrated gradients, all normalised to one `ExplanationResult`. Temporal attribution and `trend │ spike │ level_shift` concept segmentation. |
| `glassbox.py` | EBM second opinion; `shap_vs_ebm_top3_jaccard < 0.34` flags model disagreement. |
| `reason_card.py` | Failure mode + top attributions → KB card (en/hi). Returns `None` for an unknown mode rather than inventing a repair. |
| `counterfactual.py` | Constrained search over the four actionable features only. |
| `templates.py` | Deterministic en/hi narration — the ground truth an LLM paraphrase is audited against. |
| `audit.py` | Rank ≥ 2/3, sign agreement, numbers ±5%, feature vocabulary, recommendation ⊆ reason card. Failure → template text. |
| `confidence.py` | Interval width + model agreement + sensor quality + drift/OOD → label and per-signal reasons. |
| `quality.py` | Deletion/insertion AUC, PGI, SensitivityMax, sparsity, truth top-1 agreement, window Jaccard. |
| `drift.py` | KS per feature, batch ADWIN change point, Mahalanobis OOD. |
| `llm.py` | Qwen3 paraphrase. Inert without `TV_LLM_ENDPOINT`; any failure keeps the template. |

**Deliberate simplifications** (each stated in the module docstring): the counterfactual search replaces DiCE (four features on a quantised grid), and the quality metrics replace Quantus (~50 lines of numpy, so the definitions in the paper are the ones in the code).

---

## 3. Backend Modules

### M6 `app/modules/xai/`
`repository.py` / `service.py` / `router.py` + `app/workers/tasks/explain.py`. Endpoints: `/explanations/{id}`, `/predictions/{id}/explanation`, `/explanations/{id}/counterfactual`, `/explanations/{id}/narration`, `/explanations/{id}/feedback`, `/models/{id}/global-importance`, `/models/{id}/quality-metrics`, `/narration-audits`.

Narration is composed on first request, audited, and stored. Feedback naming a suspect sensor writes the flag and the feedback row in one transaction.

### M7 `app/modules/maintenance/`
- `risk.py` — fits a Weibull whose **median is the RUL point estimate** and whose shape reflects the conformal interval width; `cdf(t)` is P(failure before the slot). Single source for the Gantt overlay, the optimiser objective and `/risk`.
- `optimiser.py` — CP-SAT over 15-minute slots. Constraints: availability, skills, one order per line, one order per technician, order within horizon. Objective: downtime × priority-weighted wait + risk × failure cost + slot-tariff energy cost + labour.
- `service.py` — CRUD, closure (publishes `maintenance_reset` **before** commit, so a rejected command rolls the closure back), Gantt drag with conflict re-check, CSV/JSON/B2MML export.
- `workers/tasks/maintenance.py` — auto work orders off the **calibrated** probability only, and closure scoring.

### M8 `app/modules/analytics/`
- `oee.py` — availability/performance/quality/OEE/MTBF/MTTR. Every result carries the `inputs` it came from, which is what lands in `kpi_values.inputs` and what the UI shows on hover.
- `energy.py` — OLS baseline of kWh on units, one-sided 3σ anomaly detection, cost/CO₂/intensity summary.
- `repository.py` — aggregation in SQL over the M3 tables; no week of per-minute telemetry crosses into Python.
- `workers/tasks/rollup.py` — hourly day rollup, shift-boundary rollup, nightly baseline refit, all in the **plant's** timezone.

---

## 4. Frontend

- **`features/explain/`** — `ExplanationCard` (narration, waterfall, EBM agreement chip, reason card, counterfactual, feedback), `AttributionWaterfall`, `ReasonCardPanel`, `CounterfactualTable`, `FeedbackButtons`, `QualityPage` (`/explain/quality`).
- **`features/maintenance/`** — `MaintenancePage` (`/maintenance`), `WorkOrderDrawer` (risk trade-off ±24 h, embedded explanation, closure), `CreateWorkOrderModal`, `SchedulePage` (`/maintenance/schedule`) with an ECharts custom-series `GanttChart` — bars coloured by risk, dashed outline where a planner moved one by hand.
- **`features/analytics/`** — `ProductionPage` (`/analytics/production`), `EnergyPage` (`/analytics/energy`), shared `ScopePicker`.

---

## 5. Verification

| Suite | Result |
|---|---|
| `packages/xai` (`tests/test_xai.py`) | **40 passed** |
| `apps/api` `test_maintenance.py` + `test_analytics.py` | **50 passed** |
| `apps/web` `vitest run` | **42 passed (9 files)** |
| `ruff check` — all new backend + library code | clean |
| `tsc -b` and `eslint` — all new frontend code | clean |
| Alembic `0006→0008` offline SQL | generates; ORM and migrations agree on all 18 new tables |

Not yet run: the database-backed API tests, which need the compose `postgres` service (Docker was not available). Command: `make up && make test-api`.

`Nav.test.tsx` was failing before this change — it asserted a nav list frozen before M3 added `/`, `/explorer` and `/alarms`. Rewritten to assert role filtering as behaviour.

---

## 6. New Dependencies

`apps/api`: `ortools` (CP-SAT), `shap`, `numba` (pinned ≥0.61 so shap resolves on Python 3.12), `pyyaml`.
`packages/xai`: `shap`, `interpret-core` (EBM), `pyyaml`, numpy/pandas/scikit-learn.
