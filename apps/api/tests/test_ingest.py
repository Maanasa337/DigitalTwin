"""Ingest consumer: sensor resolution and the fact tables OEE and the energy pages read."""

import uuid
from datetime import UTC, datetime
from datetime import time as dt_time
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ingest.consumer import (
    _build_asset_map,
    _build_metric_map,
    _counter_delta,
    _load_last_states,
    _tariff_rate,
)
from app.modules.analytics.models import Tariff
from app.modules.assets.schemas import AssetCreate, ComponentSpec, SensorSpec
from app.modules.assets.service import AssetService
from app.modules.telemetry.models import AssetStateEvent
from app.modules.twin.service import TwinSyncService
from tests.conftest import SAMPLE_COMPONENTS, SAMPLE_SENSORS, USERS, FakeDitto


@pytest.fixture
def two_assets(session: Session, ditto: FakeDitto, plant_line: dict[str, Any]) -> list[str]:
    """Two machines of the same type — so they publish identically named metrics."""
    service = AssetService(session, TwinSyncService(ditto))  # type: ignore[arg-type]
    codes = ["cnc-01", "cnc-02"]
    for code in codes:
        service.create_asset(
            USERS["engineer"],
            AssetCreate(
                line_id=uuid.UUID(plant_line["line"]["id"]),
                code=code,
                name=f"CNC {code}",
                asset_type="cnc_mill",
                rated_power_kw=15,
                fidelity_level=3,
            ),
            components=[ComponentSpec(**c) for c in SAMPLE_COMPONENTS],
            sensors=[SensorSpec(**s) for s in SAMPLE_SENSORS],
        )
    session.flush()
    return codes


def test_metric_map_keeps_each_asset_sensors_apart(session: Session, two_assets: list[str]) -> None:
    """Two machines share every metric name; keying on the name alone merged them into one."""
    metric_map = _build_metric_map(session)

    for code in two_assets:
        assert ("cnc-01", "power_kw") in metric_map
        assert (code, "spindle.vib_rms") in metric_map

    # The whole point: same metric, different sensor row per asset.
    assert metric_map[("cnc-01", "power_kw")]["sensor_id"] != metric_map[("cnc-02", "power_kw")]["sensor_id"]
    assert len(metric_map) == len(two_assets) * len(SAMPLE_SENSORS)


def test_asset_map_resolves_codes_for_metrics_without_a_sensor(session: Session, two_assets: list[str]) -> None:
    """`state` and the production counters have no sensor row, so they resolve by asset code."""
    asset_map = _build_asset_map(session)
    assert set(two_assets) <= set(asset_map)


@pytest.mark.parametrize(
    ("last", "current", "expected"),
    [
        (None, 100.0, 0.0),  # first reading establishes the baseline, it is not itself production
        (100.0, 140.0, 40.0),
        (100.0, 100.0, 0.0),
        (140.0, 5.0, 0.0),  # simulator restarted and the counter reset
    ],
)
def test_counter_delta(last: float | None, current: float, expected: float) -> None:
    previous: dict[str, float] = {} if last is None else {"good_count": last}
    assert _counter_delta(previous, "good_count", current) == expected
    assert previous["good_count"] == current


def test_counter_delta_ignores_a_missing_reading() -> None:
    previous = {"good_count": 10.0}
    assert _counter_delta(previous, "good_count", None) == 0.0
    assert previous["good_count"] == 10.0


def test_tariff_rate_is_resolved_in_plant_local_time() -> None:
    night = Tariff(
        name="Off-peak",
        starts_local=dt_time(22, 0),
        ends_local=dt_time(6, 0),
        rate_per_kwh="5.5",
        days_of_week=[0, 1, 2, 3, 4, 5, 6],
    )
    entry = ("Asia/Kolkata", [night])

    # 19:00 UTC is 00:30 in Kolkata — inside the window that wraps past midnight.
    assert _tariff_rate(entry, datetime(2026, 9, 21, 19, 0, tzinfo=UTC)) == pytest.approx(5.5)
    # 09:00 UTC is 14:30 in Kolkata — outside it.
    assert _tariff_rate(entry, datetime(2026, 9, 21, 9, 0, tzinfo=UTC)) is None
    assert _tariff_rate(None, datetime(2026, 9, 21, 9, 0, tzinfo=UTC)) is None


def test_last_states_survive_a_restart(session: Session, two_assets: list[str]) -> None:
    """State events record transitions, so a restart must not re-emit the state already in force."""
    asset_map = _build_asset_map(session)
    asset_id = asset_map["cnc-01"]
    session.add(AssetStateEvent(time=datetime(2026, 9, 20, 6, tzinfo=UTC), asset_id=asset_id, state="IDLE"))
    session.add(AssetStateEvent(time=datetime(2026, 9, 20, 7, tzinfo=UTC), asset_id=asset_id, state="RUNNING"))
    session.flush()

    assert _load_last_states(session)[asset_id] == "RUNNING"


def test_fact_tables_accept_the_rows_the_consumer_builds(session: Session, two_assets: list[str]) -> None:
    """The analytics repository sums these columns; a schema drift here silently zeroes every KPI."""
    asset_id = _build_asset_map(session)["cnc-01"]
    now = datetime.now(UTC)

    session.execute(
        text(
            "INSERT INTO energy_readings "
            "(time, asset_id, power_kw, energy_kwh, power_factor, current_a, voltage_v, tariff_rate) "
            "VALUES (:time, :asset_id, :power_kw, :energy_kwh, :power_factor, :current_a, "
            ":voltage_v, :tariff_rate)"
        ),
        [
            {
                "time": now,
                "asset_id": asset_id,
                "power_kw": 12.5,
                "energy_kwh": 0.25,
                "power_factor": 0.88,
                "current_a": 19.8,
                "voltage_v": 415.0,
                "tariff_rate": "8.5000",
            }
        ],
    )
    session.execute(
        text(
            "INSERT INTO production_counts (time, asset_id, good_count, reject_count, cycle_time_s) "
            "VALUES (:time, :asset_id, :good_count, :reject_count, :cycle_time_s)"
        ),
        [{"time": now, "asset_id": asset_id, "good_count": 7, "reject_count": 1, "cycle_time_s": 48.2}],
    )
    session.flush()

    energy = session.execute(
        text("SELECT sum(energy_kwh * tariff_rate), max(power_kw) FROM energy_readings WHERE asset_id = :id"),
        {"id": asset_id},
    ).one()
    assert float(energy[0]) == pytest.approx(2.125)
    assert float(energy[1]) == pytest.approx(12.5)

    produced = session.execute(
        text("SELECT sum(good_count), sum(reject_count) FROM production_counts WHERE asset_id = :id"),
        {"id": asset_id},
    ).one()
    assert (produced[0], produced[1]) == (7, 1)


# ── Edge predictions (M11) ────────────────────────────────────────────


def _edge_message(model_version: str, **overrides: Any) -> Any:
    from twinvoice_contracts.prediction import EdgePrediction

    now = datetime.now(UTC)
    body: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "asset_code": "cnc-01",
        "time": now.isoformat(),
        "window_start": now.isoformat(),
        "window_end": now.isoformat(),
        "model_version": model_version,
        "health_index": 81.234,
        "rul": {"point": 40.0, "low": 31.0, "high": 49.0, "unit": "d", "coverage": 0.9},
        "confidence": {"label": "medium", "reasons": []},
        "explanation": {
            "method": "tree_shap",
            "base_value": 55.0,
            "attributions": [
                {"feature": "spindle.vib_rms_mean", "label": "Spindle vibration mean", "value": 3.2,
                 "unit": "mm/s", "contribution": -9.5, "direction": "lowering", "share": 0.7, "rank": 1},
            ],
        },
        "latency_ms": {"infer_ms": 1.6, "explain_ms": 7.9},
    }  # fmt: skip
    body.update(overrides)
    return EdgePrediction.model_validate(body)


@pytest.fixture
def edge_model(session: Session) -> Any:
    from app.modules.pdm.service import ModelService

    return ModelService(session).register_model(
        None,
        name="rul-synthetic-cnc_mill",
        version="2026.09.21-100000",
        task="rul",
        algorithm="lightgbm",
        dataset_ref="synthetic:cnc_mill",
        dataset_hash="x",
        feature_set={"features": ["spindle.vib_rms_mean"]},
        artifact_uri="file:///data/models/x/model.pkl",
    )


def test_an_edge_prediction_is_stored_with_its_explanation(
    session: Session, two_assets: list[str], edge_model: Any
) -> None:
    from app.ingest.edge_predictions import store_edge_prediction
    from app.modules.pdm.models import Prediction
    from app.modules.xai.models import Explanation

    asset_id = _build_asset_map(session)["cnc-01"]
    message = _edge_message("rul-synthetic-cnc_mill:2026.09.21-100000")
    stored = store_edge_prediction(session, message, asset_id)

    assert stored is not None
    row = session.scalars(select(Prediction).where(Prediction.id == stored.prediction_id)).one()
    assert row.source == "edge"
    assert row.model_id == edge_model.id
    assert row.latency_ms == 10  # 1.6 ms inference + 7.9 ms explanation
    assert (row.rul_point, row.rul_low, row.rul_high, row.rul_unit) == (40.0, 31.0, 49.0, "d")
    assert float(row.health_index) == pytest.approx(81.23)
    explanation = session.scalars(select(Explanation).where(Explanation.prediction_id == row.id)).one()
    assert explanation.method == "tree_shap"
    assert explanation.attributions[0]["feature"] == "spindle.vib_rms_mean"
    assert explanation.compute_ms == 8

    # Mirrors infer.py's live payload, so the UI handles both the same way.
    assert stored.live_payload["asset"] == "cnc-01"
    assert stored.live_payload["rul_point"] == 40.0
    assert stored.live_payload["source"] == "edge"

    # The API reports it with source 'edge' (the machine page's Edge tag reads this).
    from app.modules.pdm.schemas import PredictionOut

    assert PredictionOut.from_prediction(row).source == "edge"


def test_a_replayed_edge_prediction_is_not_stored_twice(
    session: Session, two_assets: list[str], edge_model: Any
) -> None:
    from app.ingest.edge_predictions import store_edge_prediction
    from app.modules.pdm.models import Prediction

    asset_id = _build_asset_map(session)["cnc-01"]
    message = _edge_message("rul-synthetic-cnc_mill:2026.09.21-100000")
    assert store_edge_prediction(session, message, asset_id) is not None
    assert store_edge_prediction(session, message, asset_id) is None
    assert len(session.scalars(select(Prediction).where(Prediction.id == uuid.UUID(message.id))).all()) == 1


def test_an_edge_prediction_for_an_unknown_model_is_dropped(session: Session, two_assets: list[str]) -> None:
    from app.ingest.edge_predictions import store_edge_prediction

    asset_id = _build_asset_map(session)["cnc-01"]
    assert store_edge_prediction(session, _edge_message("rul-nope:1"), asset_id) is None


def test_a_bare_model_name_resolves_to_its_production_model(session: Session, edge_model: Any) -> None:
    from app.ingest.edge_predictions import resolve_model
    from app.modules.pdm.service import ModelService

    assert resolve_model(session, "rul-synthetic-cnc_mill") is None
    ModelService(session).promote(None, edge_model.id)  # type: ignore[arg-type]
    assert resolve_model(session, "rul-synthetic-cnc_mill") == edge_model
