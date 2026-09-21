from __future__ import annotations

import math
from dataclasses import dataclass

BOLTZMANN_EV_PER_K = 8.617333262e-5
KELVIN = 273.15


@dataclass(frozen=True, slots=True)
class Arrhenius:
    """Temperature acceleration factor AF = exp(Ea/k * (1/T_ref - 1/T)), used as a rate modifier."""

    activation_energy_ev: float
    t_ref_c: float

    def factor(self, temp_c: float) -> float:
        t_k = max(temp_c + KELVIN, 1.0)
        inv_diff = 1 / (self.t_ref_c + KELVIN) - 1 / t_k
        return math.exp(min(self.activation_energy_ev / BOLTZMANN_EV_PER_K * inv_diff, 50.0))
