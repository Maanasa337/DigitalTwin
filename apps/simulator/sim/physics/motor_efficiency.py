from __future__ import annotations

from typing import ClassVar

from sim.physics.arrhenius import Arrhenius
from sim.physics.gamma import GammaProcess


class MotorEfficiencyLoss(GammaProcess):
    """Motor degradation D (Gamma wear driven by I^2R heating ~ load^2) lowering efficiency.

    eta = eta0 - k * D; failure when D = 1, i.e. efficiency has dropped by k.
    """

    model: ClassVar[str] = "motor_efficiency"

    def __init__(
        self,
        driver: str,
        life_h: float,
        eta0: float = 0.92,
        k: float = 0.12,
        cv: float = 0.15,
        load_exp: float = 2.0,
        initial: float = 0.0,
        arrhenius: Arrhenius | None = None,
    ) -> None:
        super().__init__(driver, life_h, cv, load_exp, 0.0, initial, arrhenius)
        self.eta0 = eta0
        self.k = k

    def efficiency(self) -> float:
        return self.eta0 - self.k * self.damage
