from __future__ import annotations

from typing import ClassVar

import numpy as np

from sim.physics.arrhenius import Arrhenius
from sim.physics.process import HOUR_S, Conditions, DegradationProcess


class GammaProcess(DegradationProcess):
    """Monotone wear X(t) with independent Gamma(alpha*dt, beta) increments; failure at X = 1.

    Calibrated so the mean life is `life_h` at reference conditions and the coefficient of variation
    of X at that life is `cv`: alpha*beta = 1/life and alpha*life = 1/cv^2.
    """

    model: ClassVar[str] = "gamma"

    def __init__(
        self,
        driver: str,
        life_h: float,
        cv: float = 0.2,
        load_exp: float = 1.0,
        speed_exp: float = 0.0,
        initial: float = 0.0,
        arrhenius: Arrhenius | None = None,
    ) -> None:
        super().__init__(driver, arrhenius)
        life_s = life_h * HOUR_S
        self.shape_rate = 1.0 / (cv**2 * life_s)
        self.scale = 1.0 / (self.shape_rate * life_s)
        self.load_exp = load_exp
        self.speed_exp = speed_exp
        self.x = initial

    @property
    def damage(self) -> float:
        return min(max(self.x, 0.0), 1.0)

    @property
    def mean_rate(self) -> float:
        return self.shape_rate * self.scale

    def acceleration(self, cond: Conditions) -> float:
        return max(cond.load, 0.0) ** self.load_exp * max(cond.speed, 0.0) ** self.speed_exp

    def _advance(self, reference_s: float, rng: np.random.Generator) -> None:
        self.x = min(self.x + rng.gamma(self.shape_rate * reference_s, self.scale), 1.0)

    def _remaining_reference_s(self) -> float:
        return (1.0 - self.x) / self.mean_rate

    def jump(self, amount: float) -> None:
        self.x = min(self.x + amount, 1.0)

    def _reset_state(self) -> None:
        self.x = 0.0
