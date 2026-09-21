"""Production plan following (load) and good/reject cycle counting."""

from __future__ import annotations

import math

import numpy as np

LOAD_CORRELATION_S = 300.0
LOAD_WALK_STD_PCT = 2.5
MAX_LOAD_PCT = 110.0


def follow_plan(
    load_pct: float, target_pct: float, dt: float, rng: np.random.Generator, walk: bool
) -> float:
    """Ornstein-Uhlenbeck random walk around the plan target (exact for any dt).

    An operator setpoint (`walk=False`) is held exactly.
    """
    if not walk:
        return target_pct
    decay = math.exp(-dt / LOAD_CORRELATION_S)
    noise = LOAD_WALK_STD_PCT * math.sqrt(1 - decay * decay) * rng.normal()
    return min(max(target_pct + (load_pct - target_pct) * decay + noise, 0.0), MAX_LOAD_PCT)


class ProductionCounter:
    def __init__(self, ideal_cycle_time_s: float) -> None:
        self.ideal_cycle_time_s = ideal_cycle_time_s
        self.good = 0
        self.reject = 0
        self.cycle_time_s = ideal_cycle_time_s
        self._partial = 0.0

    @property
    def total(self) -> int:
        return self.good + self.reject

    def step(
        self,
        dt: float,
        utilization: float,
        slowdown: float,
        speed: float,
        reject_prob: float,
        rng: np.random.Generator,
    ) -> None:
        """Advance `dt` seconds of running; `utilization` in [0, 1] is the busy fraction."""
        if dt <= 0 or utilization <= 0:
            return
        nominal = self.ideal_cycle_time_s / max(speed, 0.1) * (1 + slowdown)
        self.cycle_time_s = nominal * max(1 + 0.02 * rng.normal(), 0.5)
        self._partial += dt * min(utilization, 1.0) / nominal
        completed = int(self._partial)
        self._partial -= completed
        rejects = int(rng.binomial(completed, min(max(reject_prob, 0.0), 1.0))) if completed else 0
        self.good += completed - rejects
        self.reject += rejects
