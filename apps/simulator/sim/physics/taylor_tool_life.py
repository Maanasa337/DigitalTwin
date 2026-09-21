from __future__ import annotations

from typing import ClassVar

import numpy as np

from sim.physics.arrhenius import Arrhenius
from sim.physics.process import HOUR_S, Conditions, DegradationProcess


class TaylorToolLife(DegradationProcess):
    """Tool flank wear from Taylor's equation V * T^n = C, accumulated with Miner's rule.

    Tool life at cutting speed V is T(V) = (C / V)^(1/n); the wear fraction grows at 1/T(V).
    C is derived from `life_h` at the reference cutting speed. Feed (load) enters as the extended
    Taylor term load^feed_exp. Damage = VB / VB_max.
    """

    model: ClassVar[str] = "taylor"

    def __init__(
        self,
        driver: str,
        life_h: float,
        cutting_speed_m_min: float,
        n: float = 0.25,
        vb_max_mm: float = 0.3,
        feed_exp: float = 0.5,
        initial: float = 0.0,
        arrhenius: Arrhenius | None = None,
    ) -> None:
        super().__init__(driver, arrhenius)
        self.n = n
        self.v_ref = cutting_speed_m_min
        self.c = cutting_speed_m_min * (life_h * 60.0) ** n
        self.life_ref_s = life_h * HOUR_S
        self.vb_max_mm = vb_max_mm
        self.feed_exp = feed_exp
        self.wear = min(initial, 1.0)

    @property
    def damage(self) -> float:
        return self.wear

    @property
    def flank_wear_mm(self) -> float:
        return self.wear * self.vb_max_mm

    def tool_life_min(self, cutting_speed_m_min: float) -> float:
        return (self.c / cutting_speed_m_min) ** (1.0 / self.n)

    def acceleration(self, cond: Conditions) -> float:
        return max(cond.speed, 0.0) ** (1.0 / self.n) * max(cond.load, 0.0) ** self.feed_exp

    def _advance(self, reference_s: float, rng: np.random.Generator) -> None:
        self.wear = min(self.wear + reference_s / self.life_ref_s, 1.0)

    def _remaining_reference_s(self) -> float:
        return (1.0 - self.wear) * self.life_ref_s

    def jump(self, amount: float) -> None:
        self.wear = min(self.wear + amount, 1.0)

    def _reset_state(self) -> None:
        self.wear = 0.0
