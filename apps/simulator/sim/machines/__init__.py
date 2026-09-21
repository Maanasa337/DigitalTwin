"""Machine library (FR-SIM-01): one class per asset type, parameters in <asset_type>.yaml."""

from sim.machines.base import Machine, State
from sim.machines.cnc_mill import CncMill
from sim.machines.compressor import Compressor
from sim.machines.conveyor import Conveyor
from sim.machines.hydraulic_press import HydraulicPress
from sim.machines.injection_moulder import InjectionMoulder

MACHINE_CLASSES: dict[str, type[Machine]] = {
    cls.asset_type: cls for cls in (CncMill, Compressor, Conveyor, HydraulicPress, InjectionMoulder)
}

__all__ = ["MACHINE_CLASSES", "Machine", "State"]
