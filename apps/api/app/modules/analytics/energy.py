"""Energy KPIs, baseline regression and anomaly detection (FR-EN-01..03).

The baseline is a one-variable OLS of energy against production volume. That is the ISO 50001 shape
of an energy performance indicator: consumption is expected to rise with output, so "used more kWh"
is only an anomaly once output is accounted for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.modules.analytics.oee import KpiResult

ANOMALY_SIGMA = 3.0
MIN_BASELINE_POINTS = 8


@dataclass(frozen=True)
class Baseline:
    intercept_kwh: float
    slope_kwh_per_unit: float
    r2: float | None
    residual_std: float
    n: int

    def expected(self, units: float) -> float:
        return self.intercept_kwh + self.slope_kwh_per_unit * units

    def residual_sigma(self, units: float, actual_kwh: float) -> float:
        """How many standard deviations the actual consumption sits above its expected value."""
        if self.residual_std <= 0:
            return 0.0
        return (actual_kwh - self.expected(units)) / self.residual_std


@dataclass(frozen=True)
class EnergyAnomaly:
    time: datetime
    scope_id: str
    energy_kwh: float
    expected_kwh: float
    units: float
    sigma: float
    health_index: float | None = None


@dataclass(frozen=True)
class EnergySummary:
    energy_kwh: float
    cost: float
    co2_kg: float
    peak_demand_kw: float
    idle_energy_kwh: float
    energy_per_unit: float | None
    idle_energy_share: float
    currency: str = "INR"
    breakdown: list[dict[str, Any]] = field(default_factory=list)


def fit_baseline(points: list[tuple[float, float]]) -> Baseline | None:
    """OLS of kWh on units. Returns None below MIN_BASELINE_POINTS or when output never varies.

    A flat x gives an infinite slope, and a baseline fitted on four points would flag noise as
    anomalies for the rest of the month — both are worse than having no baseline.
    """
    if len(points) < MIN_BASELINE_POINTS:
        return None

    n = len(points)
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0:
        return None

    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / sxx
    intercept = mean_y - slope * mean_x

    residuals = [y - (intercept + slope * x) for x, y in points]
    ss_res = sum(r * r for r in residuals)
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
    # n-2 degrees of freedom: two parameters were estimated from these same points.
    residual_std = math.sqrt(ss_res / (n - 2)) if n > 2 else 0.0

    return Baseline(
        intercept_kwh=round(intercept, 6),
        slope_kwh_per_unit=round(slope, 6),
        r2=round(r2, 4) if r2 is not None else None,
        residual_std=round(residual_std, 6),
        n=n,
    )


def find_anomalies(
    baseline: Baseline,
    observations: list[tuple[datetime, float, float]],
    *,
    scope_id: str,
    sigma: float = ANOMALY_SIGMA,
) -> list[EnergyAnomaly]:
    """Flag periods whose consumption exceeds the baseline by more than `sigma` residual deviations.

    One-sided: consuming less energy than expected is good news, not an anomaly to raise.
    """
    out: list[EnergyAnomaly] = []
    for at, units, energy_kwh in observations:
        deviation = baseline.residual_sigma(units, energy_kwh)
        if deviation > sigma:
            out.append(
                EnergyAnomaly(
                    time=at,
                    scope_id=scope_id,
                    energy_kwh=round(energy_kwh, 3),
                    expected_kwh=round(baseline.expected(units), 3),
                    units=units,
                    sigma=round(deviation, 3),
                )
            )
    return out


def summarise(
    *,
    energy_kwh: float,
    idle_energy_kwh: float,
    peak_demand_kw: float,
    cost: float,
    good_count: int,
    grid_emission_factor: float,
    currency: str = "INR",
    breakdown: list[dict[str, Any]] | None = None,
) -> EnergySummary:
    return EnergySummary(
        energy_kwh=round(energy_kwh, 3),
        cost=round(cost, 2),
        co2_kg=round(energy_kwh * grid_emission_factor, 3),
        peak_demand_kw=round(peak_demand_kw, 3),
        idle_energy_kwh=round(idle_energy_kwh, 3),
        energy_per_unit=round(energy_kwh / good_count, 4) if good_count > 0 else None,
        idle_energy_share=round(100.0 * idle_energy_kwh / energy_kwh, 3) if energy_kwh > 0 else 0.0,
        currency=currency,
        breakdown=breakdown or [],
    )


def as_kpi_results(summary: EnergySummary) -> list[KpiResult]:
    """The three energy KPIs that belong in kpi_values alongside the production ones."""
    results = [
        KpiResult(
            "idle_energy_share",
            summary.idle_energy_share,
            {"idle_energy_kwh": summary.idle_energy_kwh, "energy_kwh": summary.energy_kwh},
        ),
        KpiResult("peak_demand", summary.peak_demand_kw, {"energy_kwh": summary.energy_kwh}),
    ]
    if summary.energy_per_unit is not None:
        results.append(
            KpiResult(
                "energy_per_unit",
                summary.energy_per_unit,
                {"energy_kwh": summary.energy_kwh, "cost": summary.cost, "currency": summary.currency},
            )
        )
    return results
