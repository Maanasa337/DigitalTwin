from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from sim.physics.arrhenius import Arrhenius

HOUR_S = 3600.0


@dataclass(frozen=True, slots=True)
class Conditions:
    """Operating point relative to the reference conditions a life was calibrated at."""

    load: float = 1.0
    speed: float = 1.0
    temp_c: float | None = None


class DegradationProcess(ABC):
    """Usage-based degradation measured in reference-seconds.

    Subclasses define how conditions accelerate wear (`acceleration`), how the state advances by an
    equivalent reference duration (`_advance`, exact for any step size) and the expected remaining
    reference-seconds from the current state (`_remaining_reference_s`).
    """

    model: ClassVar[str]

    def __init__(self, driver: str, arrhenius: Arrhenius | None = None) -> None:
        self.driver = driver
        self.arrhenius = arrhenius
        self.rate_multiplier = 1.0

    @property
    @abstractmethod
    def damage(self) -> float: ...

    @abstractmethod
    def acceleration(self, cond: Conditions) -> float: ...

    @abstractmethod
    def _advance(self, reference_s: float, rng: np.random.Generator) -> None: ...

    @abstractmethod
    def _remaining_reference_s(self) -> float: ...

    @abstractmethod
    def jump(self, amount: float) -> None: ...

    @abstractmethod
    def _reset_state(self) -> None: ...

    @property
    def failed(self) -> bool:
        return self.damage >= 1.0

    def rate(self, cond: Conditions) -> float:
        """Reference-seconds of wear accumulated per second of operation at `cond`."""
        factor = self.acceleration(cond) * self.rate_multiplier
        if self.arrhenius is not None and cond.temp_c is not None:
            factor *= self.arrhenius.factor(cond.temp_c)
        return factor

    def step(self, dt: float, cond: Conditions, rng: np.random.Generator) -> None:
        if dt <= 0 or self.failed:
            return
        reference_s = dt * self.rate(cond)
        if reference_s > 0:
            self._advance(reference_s, rng)

    def true_rul(self, cond: Conditions) -> float:
        """Expected remaining operating seconds at `cond`; inf when `cond` causes no wear."""
        if self.failed:
            return 0.0
        rate = self.rate(cond)
        if rate <= 0:
            return math.inf
        return max(self._remaining_reference_s(), 0.0) / rate

    def reset(self) -> None:
        self.rate_multiplier = 1.0
        self._reset_state()
