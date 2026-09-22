"""`python -m app.seed`: imports the simulator's catalog (plant, lines, assets, failure modes, scenarios).

Idempotent: existing codes are left as they are, failure modes and scenarios are upserted, and twins missing
from Ditto (e.g. after a volume reset) are recreated.
"""

import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.ditto import DittoClient
from app.core.errors import ProblemError
from app.modules.analytics.models import Shift, Tariff
from app.modules.analytics.repository import ShiftRepository, TariffRepository
from app.modules.assets.models import FailureMode, Line, Plant
from app.modules.assets.repository import AssetRepository, LineRepository, PlantRepository
from app.modules.assets.schemas import AssetCreate, ComponentSpec, LineCreate, PlantCreate, SensorSpec
from app.modules.assets.service import AssetService, LineService, PlantService
from app.modules.maintenance.models import Technician
from app.modules.maintenance.repository import TechnicianRepository
from app.modules.simulation.client import SimulatorClient
from app.modules.simulation.models import Scenario
from app.modules.telemetry.models import AlarmRule
from app.modules.twin.service import TwinSyncService

log = logging.getLogger("app.seed")

# Indian industrial time-of-day tariff shape: a cheap night band, a standard day, and an evening
# peak. Rates are illustrative — edit them per plant via /api/v1/tariffs.
DEFAULT_TARIFFS: tuple[dict[str, Any], ...] = (
    {
        "name": "Off-peak (night)",
        "starts_local": "22:00",
        "ends_local": "06:00",
        "rate_per_kwh": "5.5000",
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
    },
    {
        "name": "Standard (day)",
        "starts_local": "06:00",
        "ends_local": "18:00",
        "rate_per_kwh": "8.5000",
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
    },
    {
        "name": "Peak (evening)",
        "starts_local": "18:00",
        "ends_local": "22:00",
        "rate_per_kwh": "11.0000",
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
    },
)

DEFAULT_TECHNICIANS: tuple[dict[str, Any], ...] = (
    {"code": "tech-01", "name": "Ravi Kumar", "skills": ["mechanical", "hydraulic"], "hourly_cost": "450"},
    {"code": "tech-02", "name": "Anita Desai", "skills": ["electrical", "controls"], "hourly_cost": "520"},
    {"code": "tech-03", "name": "Suresh Nair", "skills": ["mechanical", "electrical"], "hourly_cost": "600"},
)

# Sensors worth watching out of the box, with the severity a sustained excursion earns.
ALARM_METRICS = {
    "spindle.vib_rms": "serious",
    "spindle.temp": "serious",
    "bearing.vib_rms": "serious",
    "motor.temp": "serious",
    "oil.temp": "warning",
    "airend.discharge_temp": "serious",
    "airend.discharge_pressure": "warning",
    "filter.dp": "warning",
    "tool.wear": "warning",
    "axis.following_error": "warning",
    "power_kw": "info",
}


@dataclass
class SeedReport:
    created: dict[str, int] = field(default_factory=dict)
    upserted: dict[str, int] = field(default_factory=dict)
    twins_restored: int = 0

    def count(self, bucket: dict[str, int], key: str) -> None:
        bucket[key] = bucket.get(key, 0) + 1


def apply_catalog(session: Session, twin_sync: TwinSyncService, catalog: dict[str, Any]) -> SeedReport:
    report = SeedReport()
    plant_data = catalog["plant"]
    plant = PlantRepository(session).get_by_code(plant_data["code"])
    if plant is None:
        plant = PlantService(session).create_plant(None, PlantCreate(**plant_data))
        report.count(report.created, "plants")

    lines: dict[str, Line] = {}
    for line_data in catalog["lines"]:
        line = LineRepository(session).get_by_code(plant.id, line_data["code"])
        if line is None:
            line = LineService(session).create_line(None, LineCreate(plant_id=plant.id, **line_data))
            report.count(report.created, "lines")
        lines[line.code] = line

    assets = AssetService(session, twin_sync)
    for item in catalog["assets"]:
        existing = AssetRepository(session).get_by_code(item["code"])
        if existing is not None:
            # Assets seeded before positions existed get the catalog's; one someone has moved keeps its own.
            if existing.position is None and item.get("position"):
                existing.position = dict(item["position"])
                report.count(report.upserted, "asset_positions")
            if twin_sync.ditto.get_thing(existing.ditto_thing_id) is None:
                components = assets.components.for_assets([existing.id])
                twin_sync.create_thing(existing, lines[item["line_code"]], plant, components)
                report.twins_restored += 1
            continue
        assets.create_asset(
            None,
            AssetCreate(line_id=lines[item["line_code"]].id, **item),
            components=[ComponentSpec(**c) for c in item["components"]],
            sensors=[SensorSpec(**s) for s in item["sensors"]],
        )
        report.count(report.created, "assets")

    for mode in catalog["failure_modes"]:
        values = {
            "asset_type": mode["asset_type"],
            "code": mode["code"],
            "name": mode["name"],
            "component_type": mode.get("component_type"),
            "description": mode.get("description"),
            "signature": {**mode["signature"], "driver": mode.get("driver")},
            "severity": mode.get("severity", 3),
        }
        session.execute(
            insert(FailureMode)
            .values(**values)
            .on_conflict_do_update(index_elements=["asset_type", "code"], set_={**values})
        )
        report.count(report.upserted, "failure_modes")

    for scenario in catalog["scenarios"]:
        values = {k: scenario.get(k) for k in ("code", "name", "description", "yaml")}
        session.execute(insert(Scenario).values(**values).on_conflict_do_update(index_elements=["code"], set_=values))
        report.count(report.upserted, "scenarios")

    seed_reference_data(session, plant, catalog, report)
    session.commit()
    return report


def seed_reference_data(session: Session, plant: Plant, catalog: dict[str, Any], report: SeedReport) -> None:
    """Shifts, tariffs, technicians and alarm rules.

    Without these the analytics and maintenance modules have nothing to divide by: no shift means
    OEE's planned-production time is zero, no tariff means every energy cost is zero, no technician
    means the scheduler has no one to assign, and no rule means no threshold alarm can ever fire.
    """
    existing_shifts = {s.code for s in ShiftRepository(session).for_plant(plant.id)}
    for shift in catalog.get("shifts", []):
        if shift["code"] in existing_shifts:
            continue
        session.add(Shift(plant_id=plant.id, **shift))
        report.count(report.created, "shifts")

    if not TariffRepository(session).all_active(plant.id):
        for tariff in DEFAULT_TARIFFS:
            session.add(Tariff(plant_id=plant.id, **tariff))
            report.count(report.created, "tariffs")

    for tech in DEFAULT_TECHNICIANS:
        if TechnicianRepository(session).by_code(tech["code"]) is not None:
            continue
        session.add(Technician(**tech))
        report.count(report.created, "technicians")

    seed_alarm_rules(session, report)


def seed_alarm_rules(session: Session, report: SeedReport) -> None:
    """One adaptive rule per sensor that has a documented valid range.

    Adaptive (3 sigma over a rolling baseline) rather than static thresholds: the simulator's operating
    points differ per machine, so a fleet-wide constant would either never fire or never stop.
    """
    rows = session.execute(
        text("""
        SELECT s.id, s.asset_id, s.metric_name FROM sensors s
        JOIN assets a ON a.id = s.asset_id
        WHERE s.deleted_at IS NULL AND a.deleted_at IS NULL
          AND s.metric_name = ANY(:metrics)
          AND NOT EXISTS (SELECT 1 FROM alarm_rules r WHERE r.sensor_id = s.id AND r.deleted_at IS NULL)
        """),
        {"metrics": list(ALARM_METRICS)},
    ).all()
    for sensor_id, asset_id, metric_name in rows:
        session.add(
            AlarmRule(
                sensor_id=sensor_id,
                asset_id=asset_id,
                kind="adaptive",
                params={"sigma": 3.0, "window": "1h", "metric": metric_name},
                severity=ALARM_METRICS[metric_name],
                enabled=True,
            )
        )
        report.count(report.created, "alarm_rules")


def fetch_catalog(simulator: SimulatorClient, wait_s: float) -> dict[str, Any]:
    deadline = time.monotonic() + wait_s
    while True:
        try:
            return simulator.request("GET", "/catalog")
        except ProblemError as exc:
            if time.monotonic() > deadline:
                raise
            log.info("waiting for simulator: %s", exc.detail)
            time.sleep(3)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    simulator = SimulatorClient(settings.simulator_url)
    ditto = DittoClient(settings.ditto_url, settings.ditto_subject)
    try:
        catalog = fetch_catalog(simulator, wait_s=120)
        with get_sessionmaker()() as session:
            report = apply_catalog(session, TwinSyncService(ditto), catalog)
    except ProblemError as exc:
        log.error("seed failed: %s %s", exc.title, exc.detail)
        return 1
    finally:
        simulator.close()
        ditto.close()
    log.info("created=%s upserted=%s twins_restored=%d", report.created, report.upserted, report.twins_restored)
    return 0


if __name__ == "__main__":
    sys.exit(main())
