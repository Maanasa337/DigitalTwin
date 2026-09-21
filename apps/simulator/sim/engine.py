"""SimPy-driven fleet: sim clock, shift changes, scenario events, faults and control operations.

The same Engine runs live (advanced by the asyncio loop) and headless (export).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import simpy

from sim.catalog import SENSOR_FAULT_KINDS, Catalog, ScenarioEvent, ScenarioSpec
from sim.machines import MACHINE_CLASSES, Machine
from sim.machines.base import FaultMode, Level, OperatingContext
from sim.noise import SensorFaultKind
from sim.shifts import ShiftCalendar

# Monday 06:00 Asia/Kolkata: start of shift A, so scenarios and exports begin in production.
SIM_EPOCH = datetime(2026, 1, 5, 0, 30, tzinfo=UTC)
LOG_SIZE = 100
BOUNDARY_EPSILON_S = 1e-3


class UnknownAssetError(KeyError):
    pass


class InvalidRequestError(ValueError):
    pass


def iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class LogEntry:
    t: datetime
    level: Level
    message: str
    asset_code: str | None


class Engine:
    def __init__(
        self,
        catalog: Catalog,
        seed: int,
        *,
        tick_s: float = 1.0,
        start: datetime = SIM_EPOCH,
        scenario: ScenarioSpec | None = None,
        on_tick: Callable[[Machine], None] | None = None,
    ) -> None:
        self.catalog = catalog
        self.seed = seed
        self.tick_s = tick_s
        self.start = start
        self.on_tick = on_tick
        self.env = simpy.Environment()
        self.log: deque[LogEntry] = deque(maxlen=LOG_SIZE)
        fleet = catalog.fleet
        self.calendar = ShiftCalendar(fleet.shifts, fleet.working_days, fleet.plant.timezone)
        self.shift = self.calendar.active(start)
        rngs = np.random.default_rng(seed).spawn(len(catalog.assets))
        self.machines: dict[str, Machine] = {
            asset.code: MACHINE_CLASSES[asset.asset_type](
                asset,
                catalog.types[asset.asset_type],
                catalog.sensor_specs(asset.code),
                fleet.ambient_c,
                fleet.maintenance_duration_s,
                rng,
            )
            for asset, rng in zip(catalog.assets, rngs, strict=True)
        }
        self._tickers: list[simpy.Process] = []
        for machine in self.machines.values():
            machine.step(0.0, self._context(machine))
            self._tickers.append(self.env.process(self._run_machine(machine)))
        self.env.process(self._shift_changes())
        if scenario is not None:
            for event in scenario.events:
                self.env.process(self._scenario_event(event))

    @property
    def now_s(self) -> float:
        return float(self.env.now)

    @property
    def sim_time(self) -> datetime:
        return self.at(self.now_s)

    def at(self, sim_s: float) -> datetime:
        return self.start + timedelta(seconds=sim_s)

    def advance(self, sim_s: float) -> None:
        """Run to now + sim_s, including events due exactly then (SimPy's `until` excludes them)."""
        target = self.env.now + sim_s
        self.env.run(until=target)
        while self.env.peek() <= target:
            self.env.step()

    def set_tick(self, tick_s: float) -> None:
        """Change the tick period; pending ticks are rescheduled so the change applies at once."""
        self.tick_s = tick_s
        for ticker in self._tickers:
            ticker.interrupt()

    def record(self, level: Level, message: str, asset_code: str | None = None) -> None:
        self.log.append(LogEntry(self.sim_time, level, message, asset_code))

    # SimPy processes -------------------------------------------------------------------------

    def _context(self, machine: Machine) -> OperatingContext:
        line = self.catalog.line_of(machine.code)
        plan = line.plan[self.shift.code] if self.shift is not None else 0.0
        return OperatingContext(self.now_s, self.shift is not None, plan)

    def _run_machine(self, machine: Machine) -> Generator[simpy.Event, Any, None]:
        last = self.now_s
        while True:
            try:
                yield self.env.timeout(self.tick_s)
            except simpy.Interrupt:
                continue
            dt, last = self.now_s - last, self.now_s
            for event in machine.step(dt, self._context(machine)):
                self.record(event.level, event.message, machine.code)
            if self.on_tick is not None:
                self.on_tick(machine)

    def _shift_changes(self) -> Generator[simpy.Event, Any, None]:
        while True:
            now = self.sim_time
            wait = (self.calendar.next_change(now) - now).total_seconds()
            yield self.env.timeout(max(wait, 0.0) + BOUNDARY_EPSILON_S)
            self.shift = self.calendar.active(self.sim_time)
            if self.shift is None:
                self.record("info", "Off shift: fleet idle")
            else:
                self.record("info", f"Shift {self.shift.code} ({self.shift.name}) started")

    def _scenario_event(self, event: ScenarioEvent) -> Generator[simpy.Event, Any, None]:
        yield self.env.timeout(event.at_h * 3600.0)
        self.record("info", f"Scenario event at {event.at_h:g} h: {event.action}", event.asset)
        try:
            self.apply_event(event)
        except (UnknownAssetError, InvalidRequestError) as exc:
            self.record("error", f"Scenario event failed: {exc}", event.asset)

    def apply_event(self, event: ScenarioEvent) -> None:
        match event.action:
            case "inject_fault" | "sensor_fault":
                assert event.failure_mode is not None
                self.inject_fault(
                    event.asset,
                    event.failure_mode,
                    event.mode,
                    event.severity,
                    event.metric,
                    event.duration_s,
                )
            case "set_load":
                assert event.load_pct is not None
                self.set_load(event.asset, event.load_pct)
            case "set_speed":
                assert event.speed_pct is not None
                self.set_speed(event.asset, event.speed_pct)
            case "reset":
                self.reset(event.asset, event.component_code)

    # Control operations ----------------------------------------------------------------------

    def machine(self, code: str) -> Machine:
        try:
            return self.machines[code]
        except KeyError:
            raise UnknownAssetError(code) from None

    def inject_fault(
        self,
        asset: str,
        failure_mode: str,
        mode: FaultMode = "gradual",
        severity: float = 0.5,
        metric: str | None = None,
        duration_s: float | None = None,
    ) -> None:
        machine = self.machine(asset)
        if not 0.0 <= severity <= 1.0:
            raise InvalidRequestError("severity must be within 0..1")
        if duration_s is not None and duration_s <= 0:
            raise InvalidRequestError("duration_s must be positive")
        if failure_mode in SENSOR_FAULT_KINDS:
            if metric is None or metric not in machine.sensor_array.index:
                raise InvalidRequestError(f"{failure_mode} needs a valid metric of {asset}")
            kind = SensorFaultKind(failure_mode)
            machine.sensor_array.inject(metric, kind, severity, self.now_s, duration_s)
            self.record("warning", f"Sensor fault {failure_mode} on {metric}", asset)
            return
        try:
            events = machine.inject(failure_mode, mode, severity)
        except KeyError:
            raise InvalidRequestError(
                f"{failure_mode} is not a failure mode of {machine.asset_type}"
            ) from None
        self.record("warning", f"Injected {mode} {failure_mode} (severity {severity:.2f})", asset)
        for event in events:
            self.record(event.level, event.message, asset)

    def set_load(self, asset: str, load_pct: float) -> None:
        machine = self.machine(asset)
        if not 0.0 <= load_pct <= 110.0:
            raise InvalidRequestError("load_pct must be within 0..110")
        machine.set_load_setpoint(float(load_pct))
        self.record("info", f"Load setpoint {load_pct:g} %", asset)

    def set_speed(self, asset: str, speed_pct: float) -> None:
        machine = self.machine(asset)
        if not 50.0 <= speed_pct <= 120.0:
            raise InvalidRequestError("speed_pct must be within 50..120")
        machine.speed_setpoint_pct = float(speed_pct)
        self.record("info", f"Speed setpoint {speed_pct:g} %", asset)

    def reset(self, asset: str, component_code: str | None = None) -> list[str]:
        machine = self.machine(asset)
        if component_code is not None and component_code not in machine.components:
            raise InvalidRequestError(f"{asset} has no component {component_code}")
        codes = machine.reset(component_code)
        self.record("info", f"Maintenance reset: {', '.join(codes)}", asset)
        return codes

    # Reporting -------------------------------------------------------------------------------

    def asset_status(self, machine: Machine) -> dict[str, Any]:
        truth = machine.ground_truth()
        return {
            "code": machine.code,
            "asset_type": machine.asset_type,
            "line_code": self.catalog.line_of(machine.code).code,
            "state": machine.state.value,
            "load_pct": round(machine.load_pct, 3),
            "speed_pct": machine.speed_setpoint_pct,
            "damage": {code: round(value, 6) for code, value in truth.damage.items()},
            "active_modes": [
                {
                    "failure_mode": active.failure_mode,
                    "mode": active.mode,
                    "severity": active.severity,
                    "started_at": iso(self.at(active.started_s)),
                }
                for component in machine.components.values()
                for active in component.active_modes
            ],
            "sensor_faults": [
                {
                    "metric": metric,
                    "kind": fault.kind.value,
                    "until": None if fault.until_s is None else iso(self.at(fault.until_s)),
                }
                for metric, fault in machine.sensor_array.faults(self.now_s)
            ],
            "true_rul_h": None if truth.true_rul_s is None else truth.true_rul_s / 3600.0,
            "driver": truth.driver,
            "failure_mode": truth.failure_mode,
        }

    def status(self) -> dict[str, Any]:
        return {
            "sim_time": iso(self.sim_time),
            "sim_elapsed_s": self.now_s,
            "assets": [self.asset_status(m) for m in self.machines.values()],
            "log": [
                {"t": iso(e.t), "level": e.level, "message": e.message, "asset_code": e.asset_code}
                for e in self.log
            ],
        }
