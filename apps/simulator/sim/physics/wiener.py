from __future__ import annotations

import math
from typing import ClassVar

import numpy as np

from sim.physics.arrhenius import Arrhenius
from sim.physics.process import HOUR_S, Conditions, DegradationProcess


class WienerProcess(DegradationProcess):
    """Non-monotone degradation level X(t) = mu*t + sigma*W(t); failure at first passage of X = 1.

    mu = 1/life so the mean first-passage time is `life_h`; sigma makes the standard deviation of X
    at that life equal to `cv`. The RUL is the inverse-Gaussian mean (1 - X)/mu.
    """

    model: ClassVar[str] = "wiener"

    def __init__(
        self,
        driver: str,
        life_h: float,
        cv: float = 0.1,
        load_exp: float = 1.0,
        speed_exp: float = 0.0,
        initial: float = 0.0,
        arrhenius: Arrhenius | None = None,
    ) -> None:
        super().__init__(driver, arrhenius)
        life_s = life_h * HOUR_S
        self.drift = 1.0 / life_s
        self.diffusion = cv / math.sqrt(life_s)
        self.load_exp = load_exp
        self.speed_exp = speed_exp
        self.level = initial
        self._failed = False

    @property
    def damage(self) -> float:
        return 1.0 if self._failed else min(max(self.level, 0.0), 1.0)

    @property
    def failed(self) -> bool:
        return self._failed

    def acceleration(self, cond: Conditions) -> float:
        return max(cond.load, 0.0) ** self.load_exp * max(cond.speed, 0.0) ** self.speed_exp

    def _advance(self, reference_s: float, rng: np.random.Generator) -> None:
        noise = self.diffusion * math.sqrt(reference_s) * rng.normal()
        self._set_level(self.level + self.drift * reference_s + noise)

    def _set_level(self, level: float) -> None:
        self.level = min(level, 1.0)
        self._failed = level >= 1.0

    def _remaining_reference_s(self) -> float:
        return (1.0 - self.level) / self.drift

    def jump(self, amount: float) -> None:
        self._set_level(self.level + amount)

    def _reset_state(self) -> None:
        self.level = 0.0
        self._failed = False
