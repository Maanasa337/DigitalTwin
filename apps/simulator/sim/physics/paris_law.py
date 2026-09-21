from __future__ import annotations

import math
from typing import ClassVar

import numpy as np

from sim.physics.arrhenius import Arrhenius
from sim.physics.process import HOUR_S, Conditions, DegradationProcess


class ParisLaw(DegradationProcess):
    """Fatigue crack growth da/dN = C (dK)^m with dK = Y * dS * sqrt(pi * a).

    Integrated in closed form, so any step size is exact:
        a^k = a0^k + k * G * N,  k = 1 - m/2,  G = C * (Y * dS * sqrt(pi))^m.
    C is derived so the crack grows from a0 to a_crit in `life_h` at reference load and `rpm`.
    Stress range scales with load and cycles with speed, so acceleration = speed * load^m.
    Damage = (a - a0) / (a_crit - a0).
    """

    model: ClassVar[str] = "paris"

    def __init__(
        self,
        driver: str,
        life_h: float,
        rpm: float,
        m: float = 3.0,
        a0_mm: float = 0.1,
        a_crit_mm: float = 2.0,
        stress_mpa: float = 120.0,
        y: float = 1.12,
        initial: float = 0.0,
        arrhenius: Arrhenius | None = None,
    ) -> None:
        if math.isclose(m, 2.0):
            raise ValueError("Paris exponent m = 2 is not supported by the closed form")
        super().__init__(driver, arrhenius)
        self.m = m
        self.k = 1.0 - m / 2.0
        self.a0 = a0_mm / 1000.0
        self.a_crit = a_crit_mm / 1000.0
        self.cycles_per_s = rpm / 60.0
        life_cycles = life_h * HOUR_S * self.cycles_per_s
        self.g = (self.a_crit**self.k - self.a0**self.k) / (self.k * life_cycles)
        self.c = self.g / (y * stress_mpa * math.sqrt(math.pi)) ** m
        self.a = self.a0
        self.jump(initial)

    @property
    def damage(self) -> float:
        return min(max((self.a - self.a0) / (self.a_crit - self.a0), 0.0), 1.0)

    @property
    def crack_mm(self) -> float:
        return self.a * 1000.0

    def acceleration(self, cond: Conditions) -> float:
        return max(cond.speed, 0.0) * max(cond.load, 0.0) ** self.m

    def remaining_cycles(self) -> float:
        return (self.a_crit**self.k - self.a**self.k) / (self.k * self.g)

    def _advance(self, reference_s: float, rng: np.random.Generator) -> None:
        target = self.a**self.k + self.k * self.g * reference_s * self.cycles_per_s
        crit = self.a_crit**self.k
        reached = target <= crit if self.k < 0 else target >= crit
        self.a = self.a_crit if reached else min(target ** (1.0 / self.k), self.a_crit)

    def _remaining_reference_s(self) -> float:
        return self.remaining_cycles() / self.cycles_per_s

    def jump(self, amount: float) -> None:
        damage = min(self.damage + amount, 1.0)
        self.a = self.a0 + damage * (self.a_crit - self.a0)

    def _reset_state(self) -> None:
        self.a = self.a0
