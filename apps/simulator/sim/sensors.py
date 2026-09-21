"""Per-asset sensor set and the full published metric set (FR-SIM-01, FR-SIM-04)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from sim.catalog import SensorSpec
from sim.noise import MeasurementModel, SensorFault, SensorFaultKind

MetricType = Literal["Double", "Int64", "String"]


@dataclass(frozen=True, slots=True)
class MetricDef:
    name: str
    datatype: MetricType
    unit: str


@dataclass(frozen=True, slots=True)
class Reading:
    value: float | None
    jitter_ms: int = 0


# Asset-level metrics beyond the catalog sensors (power_kw and load_pct are catalog sensors).
EXTRA_ASSET_METRICS = (
    MetricDef("speed_pct", "Double", "%"),
    MetricDef("energy_kwh", "Double", "kWh"),
    MetricDef("power_factor", "Double", ""),
    MetricDef("state", "String", ""),
    MetricDef("good_count", "Int64", "count"),
    MetricDef("reject_count", "Int64", "count"),
    MetricDef("cycle_time_s", "Double", "s"),
)


class SensorArray:
    def __init__(self, specs: dict[str, tuple[str | None, SensorSpec]]) -> None:
        self.metrics = list(specs)
        self.index = {metric: i for i, metric in enumerate(self.metrics)}
        self.components = [component for component, _ in specs.values()]
        sensors = [sensor for _, sensor in specs.values()]
        self.model = MeasurementModel(
            [s.noise for s in sensors],
            [s.min_valid for s in sensors],
            [s.max_valid for s in sensors],
        )
        self.metric_defs = [
            MetricDef(m, "Double", s.unit) for m, s in zip(self.metrics, sensors, strict=True)
        ]
        self.metric_defs += EXTRA_ASSET_METRICS

    def sample(
        self, clean: dict[str, float], now_s: float, dt: float, rng: np.random.Generator
    ) -> dict[str, Reading]:
        values, jitter = self.model.sample([clean[m] for m in self.metrics], now_s, dt, rng)
        return {
            metric: Reading(value, j)
            for metric, value, j in zip(self.metrics, values, jitter, strict=True)
        }

    def inject(
        self,
        metric: str,
        kind: SensorFaultKind,
        severity: float,
        now_s: float,
        duration_s: float | None,
    ) -> SensorFault:
        return self.model.inject(self.index[metric], kind, severity, now_s, duration_s)

    def clear(self, components: list[str] | None = None) -> None:
        if components is None:
            self.model.clear()
        else:
            self.model.clear([i for i, c in enumerate(self.components) if c in components])

    def faults(self, now_s: float) -> list[tuple[str, SensorFault]]:
        return [
            (self.metrics[i], fault)
            for i, fault in sorted(self.model.faults.items())
            if fault.until_s is None or fault.until_s > now_s
        ]
