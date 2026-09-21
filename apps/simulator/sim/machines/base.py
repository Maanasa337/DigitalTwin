from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar, Literal

import numpy as np

from sim.catalog import AssetSpec, ComponentSpec, FailureModeSpec, MachineTypeSpec, SensorSpec
from sim.energy import Electrical, EnergyMeter, electrical_state
from sim.physics import (
    Arrhenius,
    Conditions,
    DegradationProcess,
    GammaProcess,
    MotorEfficiencyLoss,
    ParisLaw,
    TaylorToolLife,
    WienerProcess,
)
from sim.physics.bearing_waveform import BearingGeometry, synthesize
from sim.production import ProductionCounter, follow_plan
from sim.sensors import Reading, SensorArray

GRADUAL_MIN_H = 1.0
GRADUAL_MAX_H = 24.0
LIFE_SPREAD_SIGMA = 0.15
INITIAL_DAMAGE_MAX = 0.3
MAX_REJECT_PROB = 0.5

FaultMode = Literal["gradual", "sudden"]
Level = Literal["info", "warning", "error"]


class State(StrEnum):
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    DOWN = "DOWN"
    MAINTENANCE = "MAINTENANCE"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class ActiveMode:
    failure_mode: str
    mode: FaultMode
    severity: float
    started_s: float


@dataclass(frozen=True, slots=True)
class MachineEvent:
    level: Level
    message: str


@dataclass(frozen=True, slots=True)
class GroundTruth:
    damage: dict[str, float]
    true_rul_s: float | None
    driver: str | None
    failure_mode: str


@dataclass(frozen=True, slots=True)
class OperatingContext:
    now_s: float
    producing: bool
    plan_load_pct: float


@dataclass(frozen=True, slots=True)
class Waveform:
    component_code: str
    samples: np.ndarray
    defect_freqs_hz: dict[str, float]


@dataclass(slots=True)
class Component:
    spec: ComponentSpec
    process: DegradationProcess | None
    active_modes: list[ActiveMode] = field(default_factory=list)

    @property
    def damage(self) -> float:
        return self.process.damage if self.process else 0.0

    @property
    def failure_mode(self) -> FailureModeSpec | None:
        return self.spec.failure_mode

    @property
    def temp_metric(self) -> str | None:
        return self.spec.process.temp_metric if self.spec.process else None


_PROCESS_TYPES: dict[str, type[DegradationProcess]] = {
    "wiener": WienerProcess,
    "gamma": GammaProcess,
    "arrhenius": GammaProcess,
    "paris": ParisLaw,
    "taylor": TaylorToolLife,
    "motor_efficiency": MotorEfficiencyLoss,
}


def build_process(spec: ComponentSpec, rng: np.random.Generator) -> DegradationProcess | None:
    """Instantiate a component's process with per-asset life scatter and initial wear."""
    if spec.process is None or spec.failure_mode is None:
        return None
    params = dict(spec.process.params)
    ea, t_ref = params.pop("ea_ev", None), params.pop("t_ref_c", None)
    arrhenius = Arrhenius(ea, t_ref) if ea is not None and t_ref is not None else None
    params["life_h"] *= float(rng.lognormal(0.0, LIFE_SPREAD_SIGMA))
    params["initial"] = float(rng.uniform(0.0, INITIAL_DAMAGE_MAX))
    cls = _PROCESS_TYPES[spec.process.model]
    return cls(driver=spec.failure_mode.driver, arrhenius=arrhenius, **params)  # type: ignore[arg-type]


class Machine(ABC):
    """A simulated asset: operating state, degradation, sensors, production and energy.

    Subclasses provide the clean physical signals (`_signals`) and the mechanical demand
    (`_demand`) as functions of load, speed, component damage and their own thermal states.
    """

    asset_type: ClassVar[str]

    def __init__(
        self,
        asset: AssetSpec,
        spec: MachineTypeSpec,
        sensor_specs: dict[str, tuple[str | None, SensorSpec]],
        ambient_c: float,
        maintenance_duration_s: float,
        rng: np.random.Generator,
    ) -> None:
        self.asset = asset
        self.spec = spec
        self.p = spec.params
        self.ambient_c = ambient_c
        self.maintenance_duration_s = maintenance_duration_s
        self.rng = rng
        self.components = {c.code: Component(c, build_process(c, rng)) for c in spec.components}
        self.sensor_array = SensorArray(sensor_specs)
        self.counter = ProductionCounter(asset.ideal_cycle_time_s)
        self.meter = EnergyMeter()
        self.state = State.IDLE
        self.load_pct = 0.0
        self.speed_setpoint_pct = 100.0
        self.load_setpoint_pct: float | None = None
        self.now_s = 0.0
        self._thermal: dict[str, float] = {}
        self._maintenance_left_s = 0.0
        self._failed_component: str | None = None
        self._operating_load_pct = 100.0
        self._damage: dict[str, float] = {}
        self._refresh_damage()
        self.electrical = self._electrical()
        self.clean = self._signals(0.0)
        self.readings = self.sensor_array.sample(self._sensor_inputs(), 0.0, 0.0, rng)

    @property
    def code(self) -> str:
        return self.asset.code

    # FR-SIM-01 interface ---------------------------------------------------------------------

    def sensors(self) -> dict[str, Reading]:
        return self.readings

    def production(self) -> ProductionCounter:
        return self.counter

    def power(self) -> float:
        return self.electrical.power_kw

    def step(self, dt: float, ctx: OperatingContext) -> list[MachineEvent]:
        events: list[MachineEvent] = []
        self.now_s = ctx.now_s
        manual = self.load_setpoint_pct is not None
        target = self.load_setpoint_pct if manual else ctx.plan_load_pct
        was_running = self.running
        self._update_state(dt, ctx.producing and target > 0, events)
        if self.running:
            self._operating_load_pct = target
            start = target if not was_running else self.load_pct
            self.load_pct = follow_plan(start, target, dt, self.rng, walk=not manual)
            self._degrade(dt)
            self._refresh_damage()
        else:
            self.load_pct = 0.0
        self._check_failures(events)
        self.electrical = self._electrical()
        self.meter.add(self.electrical.power_kw, dt)
        self.clean = self._signals(dt)
        self.readings = self.sensor_array.sample(self._sensor_inputs(), ctx.now_s, dt, self.rng)
        if self.running:
            slowdown, reject_prob = self._quality_effects()
            self.counter.step(
                dt, min(self.load_pct / 100.0, 1.0), slowdown, self.speed, reject_prob, self.rng
            )
        return events

    # Operating point -------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.state is State.RUNNING

    @property
    def load(self) -> float:
        return self.load_pct / 100.0 if self.running else 0.0

    @property
    def speed(self) -> float:
        return self.speed_setpoint_pct / 100.0 if self.running else 0.0

    def set_load_setpoint(self, load_pct: float) -> None:
        """Operator override of the production plan; also the new operating point for RUL."""
        self.load_setpoint_pct = load_pct
        self._operating_load_pct = load_pct

    def damage(self, component_code: str) -> float:
        return self._damage[component_code]

    def _refresh_damage(self) -> None:
        self._damage = {code: c.damage for code, c in self.components.items()}

    def lag(self, key: str, target: float, tau_s: float, dt: float) -> float:
        """First-order thermal/pneumatic lag, exact for any dt."""
        value = self._thermal.get(key, self.ambient_c)
        value = target + (value - target) * math.exp(-dt / tau_s)
        self._thermal[key] = value
        return value

    @abstractmethod
    def _signals(self, dt: float) -> dict[str, float]:
        """Clean values for every component sensor metric."""

    @abstractmethod
    def _demand(self) -> float:
        """Mechanical demand as a fraction of rated shaft power while running."""

    # Degradation and faults ------------------------------------------------------------------

    def _conditions(self, component: Component, operating: bool) -> Conditions:
        """Actual conditions, or the operating point (setpoints) used for the RUL ground truth."""
        metric = component.temp_metric
        temp = self.clean.get(metric) if metric else None
        if not operating:
            return Conditions(self.load, self.speed, temp)
        arrhenius = component.process.arrhenius if component.process else None
        if temp is not None and arrhenius is not None:
            # A cold or idle machine still runs at least at its reference temperature once loaded.
            temp = max(temp, arrhenius.t_ref_c)
        return Conditions(self._operating_load_pct / 100, self.speed_setpoint_pct / 100, temp)

    def _degrade(self, dt: float) -> None:
        for component in self.components.values():
            if component.process is not None:
                component.process.step(dt, self._conditions(component, False), self.rng)

    def _check_failures(self, events: list[MachineEvent]) -> None:
        if self.state is State.DOWN:
            return
        for component in self.components.values():
            if component.process is not None and component.process.failed:
                self._fail(component, events)
                return

    def _fail(self, component: Component, events: list[MachineEvent]) -> None:
        self.state = State.DOWN
        self.load_pct = 0.0
        self._failed_component = component.spec.code
        mode = component.failure_mode
        name = mode.name if mode else component.spec.name
        events.append(MachineEvent("error", f"{self.code} DOWN: {name} ({component.spec.code})"))

    def _update_state(self, dt: float, producing: bool, events: list[MachineEvent]) -> None:
        if self.state is State.DOWN:
            return
        if self.state is State.MAINTENANCE:
            self._maintenance_left_s -= dt
            if self._maintenance_left_s > 0:
                return
            events.append(MachineEvent("info", f"{self.code} maintenance complete"))
        self.state = State.RUNNING if producing else State.IDLE

    def component_for_mode(self, failure_mode: str) -> Component:
        for component in self.components.values():
            if component.failure_mode and component.failure_mode.code == failure_mode:
                return component
        raise KeyError(failure_mode)

    def inject(self, failure_mode: str, mode: FaultMode, severity: float) -> list[MachineEvent]:
        component = self.component_for_mode(failure_mode)
        process = component.process
        assert process is not None
        events: list[MachineEvent] = []
        if mode == "gradual":
            target_s = (GRADUAL_MAX_H - (GRADUAL_MAX_H - GRADUAL_MIN_H) * severity) * 3600.0
            rul = process.true_rul(self._conditions(component, True))
            if math.isfinite(rul) and rul > target_s:
                process.rate_multiplier *= rul / target_s
        else:
            process.jump(severity)
            self._refresh_damage()
            self._check_failures(events)
        component.active_modes.append(ActiveMode(failure_mode, mode, severity, self.now_s))
        return events

    def reset(self, component_code: str | None = None) -> list[str]:
        codes = list(self.components) if component_code is None else [component_code]
        for code in codes:
            component = self.components[code]
            if component.process is not None:
                component.process.reset()
            component.active_modes.clear()
        self._refresh_damage()
        self.sensor_array.clear(None if component_code is None else codes)
        if self._failed_component in codes:
            self._failed_component = None
        self.state = State.MAINTENANCE
        self._maintenance_left_s = self.maintenance_duration_s
        self.load_pct = 0.0
        return codes

    def ground_truth(self) -> GroundTruth:
        damage = dict(self._damage)
        if self.state is State.DOWN and self._failed_component is not None:
            mode = self.components[self._failed_component].failure_mode
            assert mode is not None
            return GroundTruth(damage, 0.0, mode.driver, mode.code)
        best: tuple[float, FailureModeSpec] | None = None
        for component in self.components.values():
            if component.process is None or component.failure_mode is None:
                continue
            rul = component.process.true_rul(self._conditions(component, True))
            if best is None or rul < best[0]:
                best = (rul, component.failure_mode)
        if best is None or not math.isfinite(best[0]):
            return GroundTruth(damage, None, None, "none")
        return GroundTruth(damage, best[0], best[1].driver, best[1].code)

    # Energy, production, outputs ------------------------------------------------------------

    def efficiency(self) -> float:
        for component in self.components.values():
            if isinstance(component.process, MotorEfficiencyLoss):
                return component.process.efficiency()
        return self.spec.eta_nominal

    def _electrical(self) -> Electrical:
        return electrical_state(
            rated_kw=self.asset.rated_power_kw,
            demand=self._demand() if self.running else 0.0,
            efficiency=self.efficiency(),
            eta_nominal=self.spec.eta_nominal,
            idle_fraction=self.spec.idle_power_fraction,
            running=self.running,
            pf_rated=self.spec.power_factor_rated,
        )

    def _quality_effects(self) -> tuple[float, float]:
        slowdown = 0.0
        reject_prob = self.spec.base_reject_rate
        for code, component in self.components.items():
            mode = component.failure_mode
            if mode is not None:
                slowdown += mode.cycle_impact * self._damage[code] ** 2
                reject_prob += mode.quality_impact * self._damage[code] ** 2
        return slowdown, min(reject_prob, MAX_REJECT_PROB)

    def _sensor_inputs(self) -> dict[str, float]:
        return self.clean | {"power_kw": self.electrical.power_kw, "load_pct": self.load_pct}

    def metric_values(self) -> dict[str, float | int | str | None]:
        values: dict[str, float | int | str | None] = {m: r.value for m, r in self.readings.items()}
        values.update(
            speed_pct=self.speed * 100.0,
            energy_kwh=self.meter.kwh,
            power_factor=self.electrical.power_factor,
            state=self.state.value,
            good_count=self.counter.good,
            reject_count=self.counter.reject,
            cycle_time_s=self.counter.cycle_time_s,
        )
        return values

    def waveforms(self, rng: np.random.Generator) -> list[Waveform]:
        out = []
        if not self.running:
            return out
        for component in self.components.values():
            bearing = component.spec.bearing
            if bearing is None:
                continue
            geometry = BearingGeometry(
                bearing.n_balls, bearing.ball_d_mm, bearing.pitch_d_mm, bearing.contact_angle_deg
            )
            shaft_hz = bearing.shaft_rpm / 60.0 * self.speed
            samples = synthesize(geometry, shaft_hz, rng, outer=component.damage)
            freqs = {k: v for k, v in geometry.defect_frequencies(shaft_hz).items() if k != "ftf"}
            out.append(Waveform(component.spec.code, samples, freqs))
        return out
