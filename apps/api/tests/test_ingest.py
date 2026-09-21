"""Ingest consumer: sensor resolution and the fact tables OEE and the energy pages read."""

import uuid
from datetime import UTC, datetime
from datetime import time as dt_time
from typing import Any

import pytest
from sqlalchemy import text
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
