"""Failure risk before a proposed slot (FR-MS-04).

The RUL model gives a point estimate with a conformal interval, not a distribution. A two-parameter
Weibull is fitted so that its median lands on the point estimate and its spread matches the interval;
P(failure before t) is then that Weibull's CDF. This is the one place the conversion happens, so the
Gantt overlay, the optimiser objective and the /risk endpoint cannot disagree about a number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

COVERAGE_Z = 1.645  # two-sided 90% conformal interval, the default coverage in the PDM package
MIN_SHAPE = 0.5
MAX_SHAPE = 20.0


@dataclass(frozen=True)
class Weibull:
    shape: float
    scale: float

    def cdf(self, t: float) -> float:
        """P(failure by time t), with t in the same unit as the RUL estimate."""
        if t <= 0:
            return 0.0
        return 1.0 - math.exp(-((t / self.scale) ** self.shape))


def fit_weibull(point: float, low: float | None, high: float | None) -> Weibull:
    """Fit a Weibull whose median is `point` and whose spread reflects the conformal interval.

    A wide interval means an uncertain life, which is a small shape parameter (a long tail of early
    failures); a tight interval means a sharply peaked wear-out, which is a large shape parameter.
    """
    point = max(float(point), 1e-6)
    if low is None or high is None or high <= low:
        shape = 4.0  # no interval: assume ordinary wear-out
    else:
        # For a Weibull, log(t) has spread ~ 1/shape; match that to the observed log-interval width.
        log_width = math.log(max(float(high), 1e-6)) - math.log(max(float(low), 1e-6))
        shape = (2 * COVERAGE_Z) / log_width if log_width > 0 else MAX_SHAPE
    shape = min(max(shape, MIN_SHAPE), MAX_SHAPE)
    # Scale is set so the median equals the point estimate: median = scale * (ln 2)^(1/shape).
    scale = point / (math.log(2.0) ** (1.0 / shape))
    return Weibull(shape=shape, scale=scale)


def risk_before(
    *,
    rul_point: float | None,
    rul_low: float | None,
    rul_high: float | None,
    now: datetime,
    slot_start: datetime,
    rul_unit: str = "cycles",
    cycles_per_hour: float = 1.0,
) -> float:
    """P(the asset fails before `slot_start`). Returns 0 when there is no RUL to reason about."""
    if rul_point is None:
        return 0.0
    hours = (slot_start - now).total_seconds() / 3600.0
    if hours <= 0:
        return 0.0
    elapsed = hours if rul_unit == "hours" else hours * cycles_per_hour
    return round(fit_weibull(rul_point, rul_low, rul_high).cdf(elapsed), 6)


def risk_delta(
    *,
    rul_point: float | None,
    rul_low: float | None,
    rul_high: float | None,
    now: datetime,
    slot_start: datetime,
    shift_hours: float = 24.0,
    rul_unit: str = "cycles",
    cycles_per_hour: float = 1.0,
) -> dict[str, float]:
    """Risk at the slot, and what moving it ±`shift_hours` would do — the trade-off a planner needs."""
    kwargs = {
        "rul_point": rul_point,
        "rul_low": rul_low,
        "rul_high": rul_high,
        "now": now,
        "rul_unit": rul_unit,
        "cycles_per_hour": cycles_per_hour,
    }
    at_slot = risk_before(slot_start=slot_start, **kwargs)  # type: ignore[arg-type]
    return {
        "risk": at_slot,
        "risk_earlier": risk_before(slot_start=slot_start - timedelta(hours=shift_hours), **kwargs),  # type: ignore[arg-type]
        "risk_later": risk_before(slot_start=slot_start + timedelta(hours=shift_hours), **kwargs),  # type: ignore[arg-type]
        "shift_hours": shift_hours,
    }
