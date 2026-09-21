import copy
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.analytics.models import Shift, Tariff
from app.modules.assets.models import Asset, FailureMode, Sensor
from app.modules.maintenance.models import Technician
from app.modules.simulation.models import Scenario
from app.modules.telemetry.models import AlarmRule
from app.modules.twin.service import TwinSyncService
from app.seed import apply_catalog
from tests.conftest import SAMPLE_COMPONENTS, SAMPLE_SENSORS, FakeDitto

CATALOG: dict[str, Any] = {
    "plant": {"code": "plant-01", "name": "Pune Plant", "timezone": "Asia/Kolkata"},
    "lines": [{"code": "line-01", "name": "Machining Line", "sequence": 1}],
    "assets": [
        {
            "code": "cnc-01", "name": "CNC Mill 01", "asset_type": "cnc_mill", "line_code": "line-01",
            "manufacturer": "Acme", "model": "VMC-850", "serial_no": "S1", "install_date": "2023-04-01",
            "fidelity_level": 3, "ideal_cycle_time_s": 90.0, "rated_power_kw": 15.0,
            "position": {"x": 0, "y": 0, "z": 0, "rot": 0},
            "components": SAMPLE_COMPONENTS, "sensors": SAMPLE_SENSORS,
            "modbus": {"unit_id": 1, "registers": {"state": 0}},
        }
    ],
    "failure_modes": [
        {
            "asset_type": "cnc_mill", "code": "bearing_wear", "name": "Spindle bearing wear", "component_type": "spindle",
            "description": "d", "signature": {"metrics": ["spindle.vib_rms"], "pattern": "trend"}, "severity": 3,
            "driver": "spindle.vib_rms",
        }
    ],
    "scenarios": [{"code": "demo_day", "name": "Demo day", "description": None, "yaml": "code: demo_day\n"}],
    "shifts": [
        {"code": "A", "name": "Morning", "starts_local": "06:00", "ends_local": "14:00", "days_of_week": [0, 1, 2, 3, 4]}
    ],
}  # fmt: skip


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_seed_is_idempotent_and_upserts_reference_data(session: Session, ditto: FakeDitto) -> None:
    sync = TwinSyncService(ditto)  # type: ignore[arg-type]
    first = apply_catalog(session, sync, CATALOG)
    # The reference data the analytics and maintenance modules divide by is seeded alongside the
    # catalog: without it OEE has no planned time, energy has no rate and the scheduler has no one.
    assert first.created == {
        "plants": 1,
        "lines": 1,
        "assets": 1,
        "shifts": 1,
        "tariffs": 3,
        "technicians": 3,
        "alarm_rules": 2,
    }
    assert count(session, Sensor) == 3
    assert "twinvoice:cnc-01" in ditto.things

    changed = copy.deepcopy(CATALOG)
    changed["failure_modes"][0]["name"] = "Bearing wear (revised)"
    changed["scenarios"][0]["yaml"] = "code: demo_day\nseed: 9\n"
    second = apply_catalog(session, sync, changed)

    assert second.created == {}
    assert (count(session, Asset), count(session, FailureMode), count(session, Scenario)) == (1, 1, 1)
    # A second run must not duplicate the reference data either.
    assert (count(session, Shift), count(session, Tariff)) == (1, 3)
    assert (count(session, Technician), count(session, AlarmRule)) == (3, 2)
    mode = session.scalars(select(FailureMode)).one()
    assert mode.name == "Bearing wear (revised)"
    assert mode.signature["driver"] == "spindle.vib_rms"
    assert session.scalars(select(Scenario.yaml)).one().endswith("seed: 9\n")


def test_seed_restores_twins_lost_from_the_store(session: Session, ditto: FakeDitto) -> None:
    sync = TwinSyncService(ditto)  # type: ignore[arg-type]
    apply_catalog(session, sync, CATALOG)
    ditto.things.clear()

    report = apply_catalog(session, sync, CATALOG)

    assert report.twins_restored == 1
    assert set(ditto.things["twinvoice:cnc-01"]["features"]["components"]["properties"]) == {"spindle", "motor"}
