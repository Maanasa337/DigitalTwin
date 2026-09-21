"""Electrical model: input power from demand and motor efficiency, power factor and current."""

from __future__ import annotations

import math
from dataclasses import dataclass

LINE_VOLTAGE_V = 415.0


@dataclass(frozen=True, slots=True)
class Electrical:
    power_kw: float
    power_factor: float
    current_a: float


def power_factor(demand: float, pf_rated: float) -> float:
    """Induction motors run at a poor power factor when lightly loaded."""
    return pf_rated * (1.0 - 0.4 * math.exp(-4.0 * max(demand, 0.0)))


def electrical_state(
    rated_kw: float,
    demand: float,
    efficiency: float,
    eta_nominal: float,
    idle_fraction: float,
    running: bool,
    pf_rated: float,
) -> Electrical:
    """Rated power is the input at full demand with nominal efficiency; losses scale with 1/eta."""
    if running:
        shaft = idle_fraction + (1.0 - idle_fraction) * max(demand, 0.0)
        power = rated_kw * shaft * eta_nominal / max(efficiency, 0.05)
        pf = power_factor(demand, pf_rated)
    else:
        power = rated_kw * idle_fraction
        pf = power_factor(0.0, pf_rated)
    current = power * 1000.0 / (math.sqrt(3) * LINE_VOLTAGE_V * pf)
    return Electrical(power, pf, current)


class EnergyMeter:
    def __init__(self) -> None:
        self.kwh = 0.0

    def add(self, power_kw: float, dt_s: float) -> None:
        self.kwh += power_kw * dt_s / 3600.0
