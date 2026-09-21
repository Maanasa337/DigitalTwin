"""Repository layer for production and energy analytics (M8).

The aggregation queries run in SQL: pulling a week of per-minute telemetry into Python to sum it
would move megabytes per page load, and TimescaleDB already has the continuous aggregates.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import ColumnElement, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.common.repository import CrudRepository
from app.modules.analytics.models import EnergyBaseline, KpiDefinition, KpiValue, Shift, Tariff


class ShiftRepository(CrudRepository[Shift]):
    model = Shift
    sortable = frozenset({"created_at", "code", "starts_local"})
    default_sort = "code"

    def for_plant(self, plant_id: uuid.UUID) -> list[Shift]:
        return self.all([Shift.plant_id == plant_id])


class TariffRepository(CrudRepository[Tariff]):
    model = Tariff
    sortable = frozenset({"created_at", "name", "starts_local"})
    default_sort = "starts_local"

    def all_active(self, plant_id: uuid.UUID | None = None) -> list[Tariff]:
        filters: list[ColumnElement[bool]] = []
        if plant_id:
            filters.append(Tariff.plant_id == plant_id)
        return self.all(filters)

    @staticmethod
    def rate_at(tariffs: list[Tariff], at: datetime) -> float:
        """The rate in force at `at`. Windows that wrap past midnight are handled explicitly."""
        weekday = at.weekday()
        clock = at.time()
        for tariff in tariffs:
            if weekday not in (tariff.days_of_week or []):
                continue
            if _within(clock, tariff.starts_local, tariff.ends_local):
                return float(tariff.rate_per_kwh)
        return 0.0


class KpiRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def definitions(self) -> list[KpiDefinition]:
        return list(self.session.scalars(select(KpiDefinition).order_by(KpiDefinition.code)))

    def definition(self, code: str) -> KpiDefinition | None:
        return self.session.get(KpiDefinition, code)

    def values(
        self,
        *,
        scope: str,
        scope_id: uuid.UUID,
        period: str,
        start: datetime,
        end: datetime,
        codes: list[str] | None = None,
    ) -> list[KpiValue]:
        stmt = select(KpiValue).where(
            KpiValue.scope == scope,
            KpiValue.scope_id == scope_id,
            KpiValue.period == period,
            KpiValue.time >= start,
            KpiValue.time < end,
        )
        if codes:
            stmt = stmt.where(KpiValue.kpi_code.in_(codes))
        return list(self.session.scalars(stmt.order_by(KpiValue.time)))

    def upsert_many(self, rows: list[dict[str, Any]]) -> int:
        """Re-running the rollup for an open period must overwrite, not accumulate duplicates."""
        if not rows:
            return 0
        stmt = insert(KpiValue).values(rows)
        self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=["time", "period", "scope", "scope_id", "kpi_code"],
                set_={
                    "value": stmt.excluded.value,
                    "inputs": stmt.excluded.inputs,
                    "formula_version": stmt.excluded.formula_version,
                },
            )
        )
        self.session.flush()
        return len(rows)


class AnalyticsQueryRepository:
    """Raw aggregation over the M3 telemetry tables, keyed by scope."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def asset_ids(self, scope: str, scope_id: uuid.UUID) -> list[uuid.UUID]:
        if scope == "asset":
            return [scope_id]
        if scope == "line":
            sql = "SELECT id FROM assets WHERE line_id = :id AND deleted_at IS NULL"
        else:
            sql = """
                SELECT a.id FROM assets a JOIN lines l ON l.id = a.line_id
                WHERE l.plant_id = :id AND a.deleted_at IS NULL AND l.deleted_at IS NULL
            """
        return [row[0] for row in self.session.execute(text(sql), {"id": scope_id}).all()]

    def state_events(
        self, asset_ids: list[uuid.UUID], start: datetime, end: datetime
    ) -> list[tuple[datetime, str, str | None]]:
        """Events inside the period, plus the one in force at its start so the first span is complete."""
        if not asset_ids:
            return []
        rows = self.session.execute(
            text(
                """
                (SELECT time, state, cause_code FROM asset_state_events
                 WHERE asset_id = ANY(:ids) AND time >= :start AND time < :end)
                UNION ALL
                (SELECT time, state, cause_code FROM asset_state_events
                 WHERE asset_id = ANY(:ids) AND time < :start
                 ORDER BY time DESC LIMIT 1)
                ORDER BY time
                """
            ),
            {"ids": asset_ids, "start": start, "end": end},
        ).all()
        return [(row[0], row[1], row[2]) for row in rows]

    def production(self, asset_ids: list[uuid.UUID], start: datetime, end: datetime) -> dict[str, Any]:
        if not asset_ids:
            return {"good": 0, "reject": 0, "planned": 0, "cycle_times": []}
        row = self.session.execute(
            text(
                """
                SELECT coalesce(sum(good_count),0), coalesce(sum(reject_count),0),
                       coalesce(sum(good_count + reject_count) FILTER (WHERE planned),0)
                FROM production_counts
                WHERE asset_id = ANY(:ids) AND time >= :start AND time < :end
                """
            ),
            {"ids": asset_ids, "start": start, "end": end},
        ).one()
        cycle_times = [
            float(r[0])
            for r in self.session.execute(
                text(
                    """
                    SELECT cycle_time_s FROM production_counts
                    WHERE asset_id = ANY(:ids) AND time >= :start AND time < :end AND cycle_time_s IS NOT NULL
                    """
                ),
                {"ids": asset_ids, "start": start, "end": end},
            ).all()
        ]
        return {"good": int(row[0]), "reject": int(row[1]), "planned": int(row[2]), "cycle_times": cycle_times}

    def energy(self, asset_ids: list[uuid.UUID], start: datetime, end: datetime) -> dict[str, Any]:
        if not asset_ids:
            return {"energy_kwh": 0.0, "peak_kw": 0.0, "cost": 0.0}
        row = self.session.execute(
            text(
                """
                SELECT coalesce(sum(energy_kwh),0), coalesce(max(power_kw),0),
                       coalesce(sum(energy_kwh * coalesce(tariff_rate,0)),0)
                FROM energy_readings
                WHERE asset_id = ANY(:ids) AND time >= :start AND time < :end
                """
            ),
            {"ids": asset_ids, "start": start, "end": end},
        ).one()
        return {"energy_kwh": float(row[0]), "peak_kw": float(row[1]), "cost": float(row[2])}

    def idle_energy(self, asset_ids: list[uuid.UUID], start: datetime, end: datetime) -> float:
        """Energy drawn while the asset was not RUNNING — the share a plant can most cheaply remove."""
        if not asset_ids:
            return 0.0
        value = self.session.execute(
            text(
                """
                SELECT coalesce(sum(e.energy_kwh), 0)
                FROM energy_readings e
                WHERE e.asset_id = ANY(:ids) AND e.time >= :start AND e.time < :end
                  AND (
                    SELECT s.state FROM asset_state_events s
                    WHERE s.asset_id = e.asset_id AND s.time <= e.time
                    ORDER BY s.time DESC LIMIT 1
                  ) IN ('IDLE', 'DOWN')
                """
            ),
            {"ids": asset_ids, "start": start, "end": end},
        ).scalar()
        return float(value or 0.0)

    def energy_by_asset(
        self, asset_ids: list[uuid.UUID], start: datetime, end: datetime, limit: int = 5
    ) -> list[dict[str, Any]]:
        if not asset_ids:
            return []
        rows = self.session.execute(
            text(
                """
                SELECT a.code, a.name, coalesce(sum(e.energy_kwh),0) AS kwh
                FROM energy_readings e JOIN assets a ON a.id = e.asset_id
                WHERE e.asset_id = ANY(:ids) AND e.time >= :start AND e.time < :end
                GROUP BY a.code, a.name
                ORDER BY kwh DESC
                LIMIT :limit
                """
            ),
            {"ids": asset_ids, "start": start, "end": end, "limit": limit},
        ).all()
        return [{"asset_code": r[0], "asset_name": r[1], "energy_kwh": float(r[2])} for r in rows]

    def hourly_energy_and_output(
        self, asset_ids: list[uuid.UUID], start: datetime, end: datetime
    ) -> list[tuple[datetime, float, float]]:
        """(bucket, units, kWh) per hour — the observation set the baseline regression is fitted on."""
        if not asset_ids:
            return []
        rows = self.session.execute(
            text(
                """
                WITH e AS (
                    SELECT time_bucket('1 hour', time) AS bucket, sum(energy_kwh) AS kwh
                    FROM energy_readings
                    WHERE asset_id = ANY(:ids) AND time >= :start AND time < :end
                    GROUP BY bucket
                ), p AS (
                    SELECT time_bucket('1 hour', time) AS bucket, sum(good_count + reject_count) AS units
                    FROM production_counts
                    WHERE asset_id = ANY(:ids) AND time >= :start AND time < :end
                    GROUP BY bucket
                )
                SELECT e.bucket, coalesce(p.units, 0), e.kwh
                FROM e LEFT JOIN p ON p.bucket = e.bucket
                ORDER BY e.bucket
                """
            ),
            {"ids": asset_ids, "start": start, "end": end},
        ).all()
        return [(row[0], float(row[1]), float(row[2])) for row in rows]

    def breakdowns(self, asset_ids: list[uuid.UUID], start: datetime, end: datetime) -> int:
        if not asset_ids:
            return 0
        return int(
            self.session.execute(
                text(
                    """
                    SELECT count(*) FROM asset_state_events
                    WHERE asset_id = ANY(:ids) AND time >= :start AND time < :end
                      AND state = 'DOWN' AND coalesce(cause_code,'') = 'breakdown'
                    """
                ),
                {"ids": asset_ids, "start": start, "end": end},
            ).scalar()
            or 0
        )

    def repairs(self, asset_ids: list[uuid.UUID], start: datetime, end: datetime) -> tuple[float, int]:
        """Repair time and count from closed work orders' actual times (FR-PA-03)."""
        if not asset_ids:
            return 0.0, 0
        row = self.session.execute(
            text(
                """
                SELECT coalesce(sum(extract(epoch from (actual_end - actual_start))), 0), count(*)
                FROM work_orders
                WHERE asset_id = ANY(:ids) AND status = 'closed' AND deleted_at IS NULL
                  AND actual_start IS NOT NULL AND actual_end IS NOT NULL
                  AND actual_end >= :start AND actual_end < :end
                """
            ),
            {"ids": asset_ids, "start": start, "end": end},
        ).one()
        return float(row[0]), int(row[1])

    def ideal_cycle_time(self, asset_ids: list[uuid.UUID]) -> float | None:
        """Mean configured ideal cycle time across the scope's assets; None when none is configured."""
        if not asset_ids:
            return None
        value = self.session.execute(
            text("SELECT avg(ideal_cycle_time_s) FROM assets WHERE id = ANY(:ids) AND ideal_cycle_time_s IS NOT NULL"),
            {"ids": asset_ids},
        ).scalar()
        return float(value) if value is not None else None

    def plant_factors(self, scope: str, scope_id: uuid.UUID) -> tuple[float, str]:
        """(grid emission factor, currency) for the plant that owns this scope."""
        sql = {
            "plant": "SELECT grid_emission_factor_kg_per_kwh, currency FROM plants WHERE id = :id",
            "line": """SELECT p.grid_emission_factor_kg_per_kwh, p.currency FROM plants p
                       JOIN lines l ON l.plant_id = p.id WHERE l.id = :id""",
            "asset": """SELECT p.grid_emission_factor_kg_per_kwh, p.currency FROM plants p
                        JOIN lines l ON l.plant_id = p.id JOIN assets a ON a.line_id = l.id WHERE a.id = :id""",
        }[scope]
        row = self.session.execute(text(sql), {"id": scope_id}).first()
        return (float(row[0]), row[1]) if row else (0.716, "INR")


class BaselineRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest(self, scope: str, scope_id: uuid.UUID) -> EnergyBaseline | None:
        return self.session.scalars(
            select(EnergyBaseline)
            .where(EnergyBaseline.scope == scope, EnergyBaseline.scope_id == scope_id)
            .order_by(EnergyBaseline.created_at.desc())
        ).first()

    def create(self, baseline: EnergyBaseline) -> EnergyBaseline:
        self.session.add(baseline)
        self.session.flush()
        return baseline


def _within(clock: time, start: time, end: time) -> bool:
    """Inclusive of start, exclusive of end; a window where end <= start wraps past midnight."""
    if start <= end:
        return start <= clock < end
    return clock >= start or clock < end
