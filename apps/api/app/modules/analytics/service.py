"""Service layer for production and energy analytics (M8).

These methods are the single source of the numbers the analytics pages show, the KPI rollup writes,
and (per the architecture, FR-EN-06) the M10 report generator will read.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.common.service import CrudService
from app.core.audit import write_audit
from app.core.errors import NotFoundError, UnprocessableError
from app.core.security import CurrentUser
from app.modules.analytics import energy as energy_lib
from app.modules.analytics import oee as oee_lib
from app.modules.analytics.models import EnergyBaseline, Shift, Tariff
from app.modules.analytics.repository import (
    AnalyticsQueryRepository,
    BaselineRepository,
    KpiRepository,
    ShiftRepository,
    TariffRepository,
)
from app.modules.analytics.schemas import BaselineCreate, ShiftCreate, TariffCreate

TREND_BUCKETS = 12
CYCLE_TIME_BINS = 10


class KpiService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = KpiRepository(session)
        self.query = AnalyticsQueryRepository(session)

    def definitions(self) -> list[Any]:
        return self.repo.definitions()

    def series(
        self, *, scope: str, scope_id: uuid.UUID, period: str, start: datetime, end: datetime, codes: list[str] | None
    ) -> list[dict[str, Any]]:
        """Stored KPI values grouped by code, each carrying its own formula for the hover tooltip."""
        values = self.repo.values(scope=scope, scope_id=scope_id, period=period, start=start, end=end, codes=codes)
        definitions = {d.code: d for d in self.repo.definitions()}

        grouped: dict[str, list[dict[str, Any]]] = {}
        for value in values:
            grouped.setdefault(value.kpi_code, []).append(
                {"time": value.time, "value": value.value, "inputs": value.inputs}
            )
        return [
            {
                "kpi_code": code,
                "name": definitions[code].name if code in definitions else code,
                "unit": definitions[code].unit if code in definitions else "",
                "formula": definitions[code].formula if code in definitions else "",
                "points": points,
            }
            for code, points in sorted(grouped.items())
        ]

    def oee(self, *, scope: str, scope_id: uuid.UUID, period: str, start: datetime, end: datetime) -> dict[str, Any]:
        """Compute OEE for the window now, plus a trend of the same window split into buckets."""
        results = self._compute_production(scope, scope_id, start, end)
        by_code = {r.code: r for r in results}
        return {
            "scope": scope,
            "scope_id": scope_id,
            "period": period,
            "from": start,
            "to": end,
            "oee": by_code["oee"].value,
            "availability": by_code["availability"].value,
            "performance": by_code["performance"].value,
            "quality": by_code["quality"].value,
            "inputs": {code: result.inputs for code, result in by_code.items()},
            "trend": self._oee_trend(scope, scope_id, start, end),
        }

    def reliability(self, *, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime) -> dict[str, Any]:
        results = {r.code: r for r in self._compute_production(scope, scope_id, start, end)}
        return {
            "scope_id": scope_id,
            "mtbf_h": results["mtbf"].value,
            "mttr_h": results["mttr"].value,
            "breakdowns": int(results["mtbf"].inputs.get("breakdowns", 0)),
            "repairs": int(results["mttr"].inputs.get("repairs", 0)),
        }

    def downtime_pareto(self, *, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime) -> dict[str, Any]:
        durations = self._durations(scope, scope_id, start, end)
        rows = oee_lib.downtime_pareto(durations)
        return {
            "scope": scope,
            "scope_id": scope_id,
            "total_seconds": round(sum(row["seconds"] for row in rows), 1),
            "rows": rows,
        }

    def production_vs_plan(self, *, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime) -> dict[str, Any]:
        asset_ids = self.query.asset_ids(scope, scope_id)
        production = self.query.production(asset_ids, start, end)
        actual = production["good"] + production["reject"]
        planned = production["planned"]
        return {
            "scope_id": scope_id,
            "planned": planned,
            "actual": actual,
            "good": production["good"],
            "reject": production["reject"],
            "attainment": round(100.0 * actual / planned, 3) if planned else 0.0,
            "cycle_time_histogram": _histogram(production["cycle_times"]),
        }

    def rollup(self, *, scope: str, scope_id: uuid.UUID, period: str, start: datetime, end: datetime) -> int:
        """Compute and upsert every KPI for one scope and period. Called by the rollup Celery task."""
        results = self._compute_production(scope, scope_id, start, end)
        results += energy_lib.as_kpi_results(self._energy_summary(scope, scope_id, start, end))
        rows = [
            {
                "time": start,
                "period": period,
                "scope": scope,
                "scope_id": scope_id,
                "kpi_code": result.code,
                "value": result.value,
                "inputs": result.inputs,
            }
            for result in results
        ]
        written = self.repo.upsert_many(rows)
        self.session.commit()
        return written

    # ── Shared computation ────────────────────────────────────────────

    def _durations(
        self, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[oee_lib.StateDuration]:
        asset_ids = self.query.asset_ids(scope, scope_id)
        events = self.query.state_events(asset_ids, start, end)
        return oee_lib.durations_from_events(events, start, end)

    def _compute_production(
        self, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[oee_lib.KpiResult]:
        asset_ids = self.query.asset_ids(scope, scope_id)
        durations = oee_lib.durations_from_events(self.query.state_events(asset_ids, start, end), start, end)
        production = self.query.production(asset_ids, start, end)
        repair_time_s, repair_count = self.query.repairs(asset_ids, start, end)
        return oee_lib.compute_all(
            durations,
            good_count=production["good"],
            reject_count=production["reject"],
            ideal_cycle_time_s=self.query.ideal_cycle_time(asset_ids),
            breakdown_count=self.query.breakdowns(asset_ids, start, end),
            repair_time_s=repair_time_s,
            repair_count=repair_count,
        )

    def _oee_trend(self, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime) -> list[dict[str, Any]]:
        step = (end - start) / TREND_BUCKETS
        if step <= timedelta(0):
            return []
        trend = []
        for bucket in range(TREND_BUCKETS):
            bucket_start = start + step * bucket
            results = {
                r.code: r.value for r in self._compute_production(scope, scope_id, bucket_start, bucket_start + step)
            }
            trend.append({"time": bucket_start, **results})
        return trend

    def _energy_summary(
        self, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime
    ) -> energy_lib.EnergySummary:
        return EnergyService(self.session).summary_object(scope, scope_id, start, end)


class EnergyService:
    entity = "energy_baselines"

    def __init__(self, session: Session) -> None:
        self.session = session
        self.query = AnalyticsQueryRepository(session)
        self.baselines = BaselineRepository(session)

    def summary_object(
        self, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime
    ) -> energy_lib.EnergySummary:
        asset_ids = self.query.asset_ids(scope, scope_id)
        totals = self.query.energy(asset_ids, start, end)
        production = self.query.production(asset_ids, start, end)
        factor, currency = self.query.plant_factors(scope, scope_id)
        return energy_lib.summarise(
            energy_kwh=totals["energy_kwh"],
            idle_energy_kwh=self.query.idle_energy(asset_ids, start, end),
            peak_demand_kw=totals["peak_kw"],
            cost=totals["cost"],
            good_count=production["good"],
            grid_emission_factor=factor,
            currency=currency,
            breakdown=self.query.energy_by_asset(asset_ids, start, end),
        )

    def summary(self, *, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime) -> dict[str, Any]:
        summary = self.summary_object(scope, scope_id, start, end)
        return {
            "scope": scope,
            "scope_id": scope_id,
            "from": start,
            "to": end,
            **{
                key: getattr(summary, key)
                for key in (
                    "energy_kwh",
                    "cost",
                    "currency",
                    "co2_kg",
                    "peak_demand_kw",
                    "idle_energy_kwh",
                    "idle_energy_share",
                    "energy_per_unit",
                    "breakdown",
                )
            },
            "intensity_trend": self._intensity_trend(scope, scope_id, start, end),
        }

    def anomalies(self, *, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Hourly consumption more than 3 sigma above the stored baseline, with the asset's health alongside."""
        baseline_row = self.baselines.latest(scope, scope_id)
        if baseline_row is None:
            return []

        observations = self.query.hourly_energy_and_output(self.query.asset_ids(scope, scope_id), start, end)
        if not observations:
            return []

        residual_std = self._residual_std(baseline_row, observations)
        baseline = energy_lib.Baseline(
            intercept_kwh=baseline_row.intercept_kwh,
            slope_kwh_per_unit=baseline_row.slope_kwh_per_unit,
            r2=baseline_row.r2,
            residual_std=residual_std,
            n=len(observations),
        )
        health = self._health_index(scope, scope_id)
        return [
            {**anomaly.__dict__, "scope_id": scope_id, "health_index": health}
            for anomaly in energy_lib.find_anomalies(
                baseline, [(at, units, kwh) for at, units, kwh in observations], scope_id=str(scope_id)
            )
        ]

    def create_baseline(self, actor: CurrentUser, data: BaselineCreate) -> EnergyBaseline:
        asset_ids = self.query.asset_ids(data.scope, data.scope_id)
        if not asset_ids:
            raise NotFoundError(f"No assets found for {data.scope} {data.scope_id}")

        observations = self.query.hourly_energy_and_output(asset_ids, data.period_start, data.period_end)
        fitted = energy_lib.fit_baseline([(units, kwh) for _, units, kwh in observations])
        if fitted is None:
            raise UnprocessableError(
                f"Not enough varying data to fit a baseline: {len(observations)} hourly points, "
                f"at least {energy_lib.MIN_BASELINE_POINTS} with varying output are required"
            )

        baseline = self.baselines.create(
            EnergyBaseline(
                scope=data.scope,
                scope_id=data.scope_id,
                period_start=data.period_start,
                period_end=data.period_end,
                intercept_kwh=fitted.intercept_kwh,
                slope_kwh_per_unit=fitted.slope_kwh_per_unit,
                r2=fitted.r2,
            )
        )
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=baseline.id,
            action="create",
            after={"scope": data.scope, "scope_id": str(data.scope_id), "r2": fitted.r2, "n": fitted.n},
        )
        self.session.commit()
        return baseline

    def _intensity_trend(self, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """kWh per hour against the baseline's expectation — the line the energy page plots."""
        observations = self.query.hourly_energy_and_output(self.query.asset_ids(scope, scope_id), start, end)
        baseline_row = self.baselines.latest(scope, scope_id)
        return [
            {
                "time": at,
                "units": units,
                "energy_kwh": round(kwh, 3),
                "intensity": round(kwh / units, 4) if units > 0 else None,
                "expected_kwh": round(baseline_row.intercept_kwh + baseline_row.slope_kwh_per_unit * units, 3)
                if baseline_row
                else None,
            }
            for at, units, kwh in observations
        ]

    def _residual_std(self, baseline_row: EnergyBaseline, observations: list[tuple[datetime, float, float]]) -> float:
        """Residual spread measured on the current window: the stored baseline keeps only its coefficients."""
        residuals = [
            kwh - (baseline_row.intercept_kwh + baseline_row.slope_kwh_per_unit * units)
            for _, units, kwh in observations
        ]
        n = len(residuals)
        if n < 3:
            return 0.0
        mean = sum(residuals) / n
        return (sum((r - mean) ** 2 for r in residuals) / (n - 1)) ** 0.5

    def _health_index(self, scope: str, scope_id: uuid.UUID) -> float | None:
        """Correlating an energy anomaly with asset health is only meaningful for a single asset."""
        if scope != "asset":
            return None
        from app.modules.pdm.repository import PredictionRepository

        prediction = PredictionRepository(self.session).latest(scope_id)
        if prediction is None or prediction.health_index is None:
            return None
        return float(prediction.health_index)


class ShiftService(CrudService[Shift]):
    entity = "shifts"
    label = "Shift"

    def __init__(self, session: Session) -> None:
        super().__init__(session, ShiftRepository(session))

    def create_shift(self, actor: CurrentUser, data: ShiftCreate) -> Shift:
        return self.create(actor, Shift(**data.model_dump()))


class TariffService(CrudService[Tariff]):
    entity = "tariffs"
    label = "Tariff"

    def __init__(self, session: Session) -> None:
        super().__init__(session, TariffRepository(session))

    def create_tariff(self, actor: CurrentUser, data: TariffCreate) -> Tariff:
        return self.create(actor, Tariff(**data.model_dump()))

    def rate_now(self, plant_id: uuid.UUID) -> float:
        return TariffRepository.rate_at(self.repo.all_active(plant_id), datetime.now(UTC))  # type: ignore[attr-defined]


def _histogram(values: list[float], bins: int = CYCLE_TIME_BINS) -> list[dict[str, Any]]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high == low:
        return [{"from": low, "to": high, "count": len(values)}]
    width = (high - low) / bins
    counts = [0] * bins
    for value in values:
        index = min(int((value - low) / width), bins - 1)
        counts[index] += 1
    return [
        {"from": round(low + i * width, 4), "to": round(low + (i + 1) * width, 4), "count": count}
        for i, count in enumerate(counts)
    ]
