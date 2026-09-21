"""Live runtime: owns the current engine, advances it every real second, fans out snapshots."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import numpy as np

from sim.catalog import Catalog
from sim.engine import Engine, InvalidRequestError, iso
from sim.machines.base import Waveform
from sim.sensors import MetricDef

log = logging.getLogger(__name__)

MIN_TIME_SCALE = 1.0
MAX_TIME_SCALE = 1000.0
WAVEFORM_PERIOD_S = 60.0


class UnknownScenarioError(KeyError):
    pass


@dataclass(frozen=True, slots=True)
class AssetSnapshot:
    code: str
    line_code: str
    values: dict[str, float | int | str | None]
    jitter_ms: dict[str, int]


class Output(Protocol):
    async def publish(self, snapshots: list[AssetSnapshot]) -> None: ...


class WaveformSink(Protocol):
    @property
    def connected(self) -> bool: ...

    def publish_waveforms(self, waves: list[tuple[str, Waveform]]) -> None: ...


class LiveRuntime:
    """Thread-safe holder of the live engine (API, MQTT callbacks and the loop all touch it)."""

    def __init__(
        self, catalog: Catalog, seed: int, time_scale: float, start: datetime | None = None
    ) -> None:
        self.catalog = catalog
        self.lock = threading.RLock()
        self.seed = seed
        self.time_scale = self._checked_scale(time_scale)
        # `start` is injectable so tests can pin the clock: the fleet's state follows the shift
        # calendar, so a wall-clock start makes any assertion about it depend on the day and hour.
        self.engine = Engine(
            catalog,
            seed,
            tick_s=self.time_scale,
            start=start or datetime.now(UTC).replace(microsecond=0),
        )
        self.metric_defs: dict[str, list[MetricDef]] = {
            code: machine.sensor_array.metric_defs for code, machine in self.engine.machines.items()
        }
        self.scenario: tuple[str, datetime] | None = None
        self.running = False
        self.engine_replaced: list[Callable[[], None]] = []
        self._wave_rng = np.random.default_rng(seed)

    @staticmethod
    def _checked_scale(factor: float) -> float:
        if not MIN_TIME_SCALE <= factor <= MAX_TIME_SCALE:
            raise InvalidRequestError(
                f"time scale must be within {MIN_TIME_SCALE:g}..{MAX_TIME_SCALE:g}"
            )
        return float(factor)

    def set_time_scale(self, factor: float) -> float:
        factor = self._checked_scale(factor)
        with self.lock:
            self.time_scale = factor
            self.engine.set_tick(factor)
            self.engine.record("info", f"Time scale set to {factor:g}x")
        return factor

    def start_scenario(self, code: str) -> dict[str, Any]:
        spec = self.catalog.scenarios.get(code)
        if spec is None:
            raise UnknownScenarioError(code)
        started = datetime.now(UTC)
        with self.lock:
            self.engine = Engine(self.catalog, spec.seed, tick_s=spec.time_scale, scenario=spec)
            self.seed = spec.seed
            self.time_scale = spec.time_scale
            self.scenario = (code, started)
            self.engine.record(
                "info", f"Scenario {code} started (seed {spec.seed}, {spec.time_scale:g}x)"
            )
        for callback in self.engine_replaced:
            callback()
        return {
            "scenario_code": code,
            "started_at": iso(started),
            "seed": spec.seed,
            "time_scale": spec.time_scale,
        }

    def status(self) -> dict[str, Any]:
        with self.lock:
            body = self.engine.status()
            scenario = self.scenario
            return {
                "sim_time": body["sim_time"],
                "sim_elapsed_s": body["sim_elapsed_s"],
                "time_scale": self.time_scale,
                "running": self.running,
                "seed": self.seed,
                "scenario": None
                if scenario is None
                else {"code": scenario[0], "started_at": iso(scenario[1])},
                "assets": body["assets"],
                "log": body["log"],
            }

    def tick(self) -> list[AssetSnapshot]:
        with self.lock:
            self.engine.advance(self.time_scale)
            return [
                AssetSnapshot(
                    code,
                    self.catalog.line_of(code).code,
                    machine.metric_values(),
                    {metric: r.jitter_ms for metric, r in machine.readings.items()},
                )
                for code, machine in self.engine.machines.items()
            ]

    def waveforms(self) -> list[tuple[str, Waveform]]:
        with self.lock:
            return [
                (code, wave)
                for code, machine in self.engine.machines.items()
                for wave in machine.waveforms(self._wave_rng)
            ]


async def run_live(
    runtime: LiveRuntime,
    outputs: list[Output],
    waveform_sink: WaveformSink | None = None,
) -> None:
    """Advance the simulation by `time_scale` sim-seconds every real second and publish."""
    loop = asyncio.get_running_loop()
    runtime.running = True
    deadline = loop.time()
    last_wave = -WAVEFORM_PERIOD_S
    try:
        while True:
            snapshots = runtime.tick()
            for output in outputs:
                try:
                    await output.publish(snapshots)
                except Exception:
                    log.exception("output %s failed", type(output).__name__)
            due = time.monotonic() - last_wave >= WAVEFORM_PERIOD_S
            if waveform_sink is not None and waveform_sink.connected and due:
                last_wave = time.monotonic()
                waveform_sink.publish_waveforms(runtime.waveforms())
            deadline += 1.0
            delay = deadline - loop.time()
            if delay < 0:
                deadline = loop.time()
            await asyncio.sleep(max(delay, 0.0))
    finally:
        runtime.running = False
