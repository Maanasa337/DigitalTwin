"""Fleet, machine-type and scenario definitions loaded from YAML, and the /catalog seed document."""

from __future__ import annotations

from datetime import date, time
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from sim.noise import NoiseParams

PACKAGE_DIR = Path(__file__).resolve().parent
FLEET_FILE = PACKAGE_DIR / "fleet.yaml"
MACHINES_DIR = PACKAGE_DIR / "machines"
SCENARIOS_DIR = PACKAGE_DIR / "scenarios"

Code = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+$")]
AssetType = Literal["cnc_mill", "compressor", "conveyor", "hydraulic_press", "injection_moulder"]
SensorKind = Literal[
    "vibration", "temperature", "current", "voltage", "power", "pressure", "flow", "speed",
    "torque", "position", "count", "other",
]  # fmt: skip
ComponentType = Literal[
    "motor", "bearing", "spindle", "pump", "belt", "heater", "valve", "tool", "screw", "seal",
    "other",
]  # fmt: skip
ProcessModel = Literal["wiener", "gamma", "paris", "arrhenius", "taylor", "motor_efficiency"]
SENSOR_FAULT_KINDS = ("sensor_stuck", "sensor_offset", "sensor_dropout", "sensor_drift")

MODBUS_STATE_REGISTER = 0
MODBUS_GOOD_REGISTER = 2
MODBUS_REJECT_REGISTER = 4
MODBUS_METRIC_BASE = 10


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SensorSpec(_Model):
    code: Code
    name: str
    unit: str
    kind: SensorKind
    sample_rate_hz: float = 1.0
    min_valid: float
    max_valid: float
    warn_low: float | None = None
    warn_high: float | None = None
    alarm_low: float | None = None
    alarm_high: float | None = None
    noise: NoiseParams = NoiseParams()


class ProcessSpec(_Model):
    model: ProcessModel
    params: dict[str, float]
    temp_metric: str | None = None  # clean signal whose temperature drives the Arrhenius factor


class Signature(_Model):
    metrics: list[str] = Field(min_length=1)
    pattern: Literal["trend", "spike", "level"]


class FailureModeSpec(_Model):
    code: Code
    name: str
    description: str
    signature: Signature
    severity: int = Field(ge=1, le=4)
    driver: str
    quality_impact: float = 0.0  # added reject probability at damage 1 (scales with damage^2)
    cycle_impact: float = 0.0  # fractional cycle-time slowdown at damage 1 (scales with damage^2)


class BearingSpec(_Model):
    n_balls: int
    ball_d_mm: float
    pitch_d_mm: float
    contact_angle_deg: float
    shaft_rpm: float


class ComponentSpec(_Model):
    code: Code
    name: str
    component_type: ComponentType
    health_weight: float = 1.0
    bearing: BearingSpec | None = None
    process: ProcessSpec | None = None
    failure_mode: FailureModeSpec | None = None
    sensors: list[SensorSpec] = []

    @model_validator(mode="after")
    def _process_needs_mode(self) -> Self:
        if (self.process is None) != (self.failure_mode is None):
            raise ValueError(f"component {self.code}: process and failure_mode go together")
        return self

    @property
    def physics_model(self) -> str:
        return self.process.model if self.process else "none"


class MachineTypeSpec(_Model):
    asset_type: AssetType
    idle_power_fraction: float
    eta_nominal: float
    power_factor_rated: float
    base_reject_rate: float
    params: dict[str, float] = {}
    power_noise: NoiseParams = NoiseParams()
    load_noise: NoiseParams = NoiseParams()
    components: list[ComponentSpec]

    def component(self, code: str) -> ComponentSpec:
        return next(c for c in self.components if c.code == code)

    @property
    def failure_modes(self) -> list[tuple[ComponentSpec, FailureModeSpec]]:
        return [(c, c.failure_mode) for c in self.components if c.failure_mode]


class Position(_Model):
    x: float
    y: float
    z: float = 0.0
    rot: float = 0.0


class AssetSpec(_Model):
    code: Code
    name: str
    asset_type: AssetType
    manufacturer: str
    model: str
    serial_no: str
    install_date: date
    fidelity_level: int = Field(default=3, ge=1, le=4)
    ideal_cycle_time_s: float
    rated_power_kw: float
    position: Position


class LineSpec(_Model):
    code: Code
    name: str
    sequence: int
    plan: dict[str, float]  # shift code -> target load %
    assets: list[AssetSpec]


class ShiftSpec(_Model):
    code: str
    name: str
    start: time
    end: time


class PlantSpec(_Model):
    code: Code
    name: str
    timezone: str


class FleetSpec(_Model):
    plant: PlantSpec
    ambient_c: float
    maintenance_duration_s: float
    working_days: list[int]  # 0 = Monday
    shifts: list[ShiftSpec]
    lines: list[LineSpec]

    @model_validator(mode="after")
    def _plans_cover_shifts(self) -> Self:
        shift_codes = {s.code for s in self.shifts}
        for line in self.lines:
            if set(line.plan) != shift_codes:
                raise ValueError(f"line {line.code}: plan must cover shifts {sorted(shift_codes)}")
        return self


class ScenarioEvent(_Model):
    at_h: float = Field(ge=0)
    action: Literal["inject_fault", "sensor_fault", "set_load", "set_speed", "reset"]
    asset: Code
    failure_mode: str | None = None
    mode: Literal["sudden", "gradual"] = "gradual"
    severity: float = Field(default=0.5, ge=0, le=1)
    metric: str | None = None
    duration_s: float | None = None
    load_pct: float | None = Field(default=None, ge=0, le=110)
    speed_pct: float | None = Field(default=None, ge=50, le=120)
    component_code: str | None = None

    @model_validator(mode="after")
    def _required_params(self) -> Self:
        needed = {
            "inject_fault": ("failure_mode",),
            "sensor_fault": ("failure_mode", "metric"),
            "set_load": ("load_pct",),
            "set_speed": ("speed_pct",),
            "reset": (),
        }[self.action]
        missing = [name for name in needed if getattr(self, name) is None]
        if missing:
            raise ValueError(f"{self.action} requires {missing}")
        return self


class ScenarioSpec(_Model):
    code: Code
    name: str
    description: str
    seed: int
    time_scale: float = Field(ge=1, le=1000)
    duration_h: float = Field(gt=0)
    events: list[ScenarioEvent] = []


def _read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


class Catalog:
    def __init__(
        self,
        fleet: FleetSpec,
        types: dict[str, MachineTypeSpec],
        scenarios: dict[str, tuple[ScenarioSpec, str]],
    ) -> None:
        self.fleet = fleet
        self.types = types
        self.scenarios = {code: spec for code, (spec, _) in scenarios.items()}
        self.scenario_yaml = {code: raw for code, (_, raw) in scenarios.items()}
        self._validate()

    @classmethod
    def load(
        cls,
        fleet_file: Path = FLEET_FILE,
        machines_dir: Path = MACHINES_DIR,
        scenarios_dir: Path = SCENARIOS_DIR,
    ) -> Catalog:
        fleet = FleetSpec.model_validate(_read_yaml(fleet_file))
        types = {}
        for path in sorted(machines_dir.glob("*.yaml")):
            spec = MachineTypeSpec.model_validate(_read_yaml(path))
            types[spec.asset_type] = spec
        scenarios = {}
        for path in sorted(scenarios_dir.glob("*.yaml")):
            raw = path.read_text(encoding="utf-8")
            spec = ScenarioSpec.model_validate(yaml.safe_load(raw))
            scenarios[spec.code] = (spec, raw)
        return cls(fleet, types, scenarios)

    @cached_property
    def assets(self) -> list[AssetSpec]:
        return [asset for line in self.fleet.lines for asset in line.assets]

    @cached_property
    def _assets_by_code(self) -> dict[str, tuple[LineSpec, AssetSpec]]:
        return {a.code: (line, a) for line in self.fleet.lines for a in line.assets}

    def asset(self, code: str) -> AssetSpec:
        return self._assets_by_code[code][1]

    def line_of(self, code: str) -> LineSpec:
        return self._assets_by_code[code][0]

    def type_of(self, code: str) -> MachineTypeSpec:
        return self.types[self.asset(code).asset_type]

    def sensor_specs(self, asset_code: str) -> dict[str, tuple[str | None, SensorSpec]]:
        """metric_name -> (component code, sensor) in canonical order: components, power, load."""
        asset = self.asset(asset_code)
        spec = self.types[asset.asset_type]
        specs: dict[str, tuple[str | None, SensorSpec]] = {
            f"{component.code}.{sensor.code}": (component.code, sensor)
            for component in spec.components
            for sensor in component.sensors
        }
        specs["power_kw"] = (None, SensorSpec(
            code="power_kw", name="Active power", unit="kW", kind="power", min_valid=0.0,
            max_valid=round(asset.rated_power_kw * 1.5, 1), noise=spec.power_noise,
        ))  # fmt: skip
        specs["load_pct"] = (None, SensorSpec(
            code="load_pct", name="Load", unit="%", kind="other", min_valid=0.0, max_valid=120.0,
            warn_high=100.0, alarm_high=110.0, noise=spec.load_noise,
        ))  # fmt: skip
        return specs

    def sensor_rows(self, asset_code: str) -> list[dict[str, Any]]:
        return [
            _sensor_row(sensor, component, metric)
            for metric, (component, sensor) in self.sensor_specs(asset_code).items()
        ]

    def modbus_registers(self, asset_code: str) -> dict[str, int]:
        registers = {
            "state": MODBUS_STATE_REGISTER,
            "good_count": MODBUS_GOOD_REGISTER,
            "reject_count": MODBUS_REJECT_REGISTER,
        }
        for i, row in enumerate(self.sensor_rows(asset_code)):
            registers[row["metric_name"]] = MODBUS_METRIC_BASE + 2 * i
        return registers

    def document(self) -> dict[str, Any]:
        fleet = self.fleet
        return {
            "plant": fleet.plant.model_dump(),
            "lines": [
                {"code": ln.code, "name": ln.name, "sequence": ln.sequence} for ln in fleet.lines
            ],
            # The shift calendar the machines actually run to. OEE's planned-production time has to
            # come from here, or availability is measured against a window nobody worked.
            "shifts": [
                {
                    "code": s.code,
                    "name": s.name,
                    "starts_local": s.start.isoformat(timespec="minutes"),
                    "ends_local": s.end.isoformat(timespec="minutes"),
                    "days_of_week": fleet.working_days,
                }
                for s in fleet.shifts
            ],
            "assets": [
                self._asset_document(unit, a) for unit, a in enumerate(self.assets, start=1)
            ],
            "failure_modes": [
                {
                    "asset_type": spec.asset_type,
                    "code": mode.code,
                    "name": mode.name,
                    "component_type": component.component_type,
                    "description": mode.description,
                    "signature": mode.signature.model_dump(),
                    "severity": mode.severity,
                    "driver": mode.driver,
                }
                for spec in self.types.values()
                for component, mode in spec.failure_modes
            ],
            "scenarios": [
                {
                    "code": s.code,
                    "name": s.name,
                    "description": s.description,
                    "yaml": self.scenario_yaml[code],
                }
                for code, s in self.scenarios.items()
            ],
        }

    def _asset_document(self, unit_id: int, asset: AssetSpec) -> dict[str, Any]:
        spec = self.types[asset.asset_type]
        doc = asset.model_dump(mode="json")
        doc["line_code"] = self.line_of(asset.code).code
        doc["components"] = [
            {
                "code": c.code,
                "name": c.name,
                "component_type": c.component_type,
                "health_weight": c.health_weight,
                "physics_model": c.physics_model,
                "physics_params": _physics_params(c),
            }
            for c in spec.components
        ]
        doc["sensors"] = self.sensor_rows(asset.code)
        doc["modbus"] = {"unit_id": unit_id, "registers": self.modbus_registers(asset.code)}
        return doc

    def _validate(self) -> None:
        missing = {a.asset_type for a in self.assets} - set(self.types)
        if missing:
            raise ValueError(f"no machine type definition for {sorted(missing)}")
        for asset in self.assets:
            metrics = self.sensor_specs(asset.code)
            spec = self.types[asset.asset_type]
            for component, mode in spec.failure_modes:
                refs = [mode.driver, *mode.signature.metrics]
                if component.process and component.process.temp_metric:
                    refs.append(component.process.temp_metric)
                unknown = [m for m in refs if m not in metrics]
                if unknown:
                    raise ValueError(f"{spec.asset_type}.{mode.code}: unknown metrics {unknown}")
        for scenario in self.scenarios.values():
            for event in scenario.events:
                self.validate_event(scenario.code, event)

    def validate_event(self, scenario_code: str, event: ScenarioEvent) -> None:
        where = f"scenario {scenario_code} @ {event.at_h} h"
        if event.asset not in self._assets_by_code:
            raise ValueError(f"{where}: unknown asset {event.asset}")
        spec = self.type_of(event.asset)
        modes = {mode.code for _, mode in spec.failure_modes}
        if event.action == "inject_fault" and event.failure_mode not in modes:
            raise ValueError(f"{where}: {event.failure_mode} is not a mode of {spec.asset_type}")
        if event.action == "sensor_fault":
            if event.failure_mode not in SENSOR_FAULT_KINDS:
                raise ValueError(f"{where}: {event.failure_mode} is not a sensor fault kind")
            if event.metric not in self.sensor_specs(event.asset):
                raise ValueError(f"{where}: unknown metric {event.metric}")
        if event.component_code and event.component_code not in {c.code for c in spec.components}:
            raise ValueError(f"{where}: unknown component {event.component_code}")


def _sensor_row(sensor: SensorSpec, component_code: str | None, metric: str) -> dict[str, Any]:
    row = sensor.model_dump(exclude={"noise"})
    row["component_code"] = component_code
    row["metric_name"] = metric
    order = [
        "code", "component_code", "metric_name", "name", "unit", "kind", "sample_rate_hz",
        "min_valid", "max_valid", "warn_low", "warn_high", "alarm_low", "alarm_high",
    ]  # fmt: skip
    return {key: row[key] for key in order}


def _physics_params(component: ComponentSpec) -> dict[str, Any]:
    if component.process is None:
        return {}
    params: dict[str, Any] = dict(component.process.params)
    if component.process.temp_metric:
        params["temp_metric"] = component.process.temp_metric
    return params
