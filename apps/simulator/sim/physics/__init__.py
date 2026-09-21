"""Degradation physics: each process exposes damage in [0, 1], true RUL and a driver label."""

from sim.physics.arrhenius import Arrhenius
from sim.physics.gamma import GammaProcess
from sim.physics.motor_efficiency import MotorEfficiencyLoss
from sim.physics.paris_law import ParisLaw
from sim.physics.process import Conditions, DegradationProcess
from sim.physics.taylor_tool_life import TaylorToolLife
from sim.physics.wiener import WienerProcess

__all__ = [
    "Arrhenius",
    "Conditions",
    "DegradationProcess",
    "GammaProcess",
    "MotorEfficiencyLoss",
    "ParisLaw",
    "TaylorToolLife",
    "WienerProcess",
]
