"""Measurement realism: noise, drift, spikes, dropout, jitter and injected sensor faults."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

DRIFT_CORRELATION_S = 24 * 3600.0
OFFSET_SPAN_FRACTION = 0.2
DRIFT_SPAN_FRACTION_PER_H = 0.05


class SensorFaultKind(StrEnum):
    STUCK = "sensor_stuck"
    OFFSET = "sensor_offset"
    DROPOUT = "sensor_dropout"
    DRIFT = "sensor_drift"


@dataclass(frozen=True, slots=True)
class NoiseParams:
    std: float = 0.0
    drift: float = 0.0  # stationary std of the slow bias, as a fraction of the valid span
    spike_prob: float = 0.0
    spike_scale: float = 0.15  # spike magnitude as a fraction of the valid span
    dropout_prob: float = 0.0
    jitter_ms: int = 0


@dataclass(slots=True)
class SensorFault:
    kind: SensorFaultKind
    severity: float
    started_s: float
    until_s: float | None
    stuck_value: float = math.nan


class MeasurementModel:
    """Turns clean physical values into what real transmitters report, for a group of sensors.

    Missing samples are None. Injected faults are applied after the random effects, so a stuck or
    offset sensor still looks plausible. Random numbers are drawn as one block per sample: sensor
    groups are small, where per-sensor numpy calls would dominate the run time.
    """

    def __init__(self, params: list[NoiseParams], min_valid: list[float], max_valid: list[float]):
        self.params = params
        self.min_valid = min_valid
        self.max_valid = max_valid
        self.span = [hi - lo for lo, hi in zip(min_valid, max_valid, strict=True)]
        self.bias = [0.0] * len(params)
        self.last: list[float | None] = [None] * len(params)
        self.faults: dict[int, SensorFault] = {}

    def inject(
        self,
        index: int,
        kind: SensorFaultKind,
        severity: float,
        now_s: float,
        duration_s: float | None,
    ) -> SensorFault:
        until = None if duration_s is None else now_s + duration_s
        last = self.last[index]
        fault = SensorFault(kind, severity, now_s, until, math.nan if last is None else last)
        self.faults[index] = fault
        return fault

    def clear(self, indices: list[int] | None = None) -> None:
        for index in list(self.faults) if indices is None else indices:
            self.faults.pop(index, None)

    def sample(
        self, clean: list[float], now_s: float, dt: float, rng: np.random.Generator
    ) -> tuple[list[float | None], list[int]]:
        """Return (values with None for missing samples, timestamp jitter in ms)."""
        n = len(clean)
        z = rng.standard_normal(2 * n).tolist()
        u = rng.random(4 * n).tolist()
        # Exact Ornstein-Uhlenbeck update keeps the slow bias bounded for any dt.
        decay = math.exp(-dt / DRIFT_CORRELATION_S)
        bias_scale = math.sqrt(1.0 - decay * decay)
        values: list[float | None] = []
        jitter: list[int] = []
        for i, p in enumerate(self.params):
            span = self.span[i]
            self.bias[i] = self.bias[i] * decay + p.drift * span * bias_scale * z[2 * i]
            value: float | None = clean[i] + self.bias[i] + p.std * z[2 * i + 1]
            u_spike, u_drop, u_shape, u_jitter = u[4 * i : 4 * i + 4]
            if u_spike < p.spike_prob:
                sign = -1.0 if u_shape < 0.5 else 1.0
                value += sign * p.spike_scale * span * (0.5 + abs(u_shape - 0.5))
            if u_drop < p.dropout_prob:
                value = None
            fault = self.faults.get(i)
            if fault is not None:
                if fault.until_s is not None and now_s >= fault.until_s:
                    del self.faults[i]
                else:
                    value = _apply_fault(fault, value, clean[i], span, now_s)
            if value is not None:
                value = min(max(value, self.min_valid[i]), self.max_valid[i])
                self.last[i] = value
            values.append(value)
            jitter.append(int(u_jitter * (2 * p.jitter_ms + 1)) - p.jitter_ms)
        return values, jitter


def _apply_fault(
    fault: SensorFault, value: float | None, clean: float, span: float, now_s: float
) -> float | None:
    match fault.kind:
        case SensorFaultKind.DROPOUT:
            return None
        case SensorFaultKind.STUCK:
            if math.isnan(fault.stuck_value):
                fault.stuck_value = clean if value is None else value
            return fault.stuck_value
        case SensorFaultKind.OFFSET:
            return None if value is None else value + fault.severity * OFFSET_SPAN_FRACTION * span
        case SensorFaultKind.DRIFT:
            if value is None:
                return None
            hours = (now_s - fault.started_s) / 3600.0
            return value + fault.severity * DRIFT_SPAN_FRACTION_PER_H * span * hours
