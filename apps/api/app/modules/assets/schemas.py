import uuid
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, Field, field_validator

from app.common.schemas import ORMModel

AssetType = Literal["cnc_mill", "compressor", "conveyor", "hydraulic_press", "injection_moulder", "other"]
AssetStatus = Literal["RUNNING", "IDLE", "DOWN", "MAINTENANCE", "UNKNOWN"]
SensorKind = Literal[
    "vibration", "temperature", "current", "voltage", "power", "pressure",
    "flow", "speed", "torque", "position", "count", "other",
]  # fmt: skip

CODE_PATTERN = r"^[a-z0-9][a-z0-9-]{1,48}$"
PART_CODE_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,48}$"


class PlantCreate(BaseModel):
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    timezone: str = "Asia/Kolkata"
    grid_emission_factor_kg_per_kwh: float = Field(0.716, ge=0)
    currency: str = Field("INR", pattern=r"^[A-Z]{3}$")

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError("unknown IANA timezone")
        return value


class PlantOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    timezone: str
    grid_emission_factor_kg_per_kwh: float
    currency: str
    created_at: datetime
    updated_at: datetime


class LineCreate(BaseModel):
    plant_id: uuid.UUID
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    sequence: int = 0


class LineOut(ORMModel):
    id: uuid.UUID
    plant_id: uuid.UUID
    code: str
    name: str
    sequence: int
    created_at: datetime
    updated_at: datetime


class Position(BaseModel):
    x: float
    y: float
    z: float = 0
    rot: float = 0


class AssetCreate(BaseModel):
    line_id: uuid.UUID
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    asset_type: AssetType
    manufacturer: str | None = None
    model: str | None = None
    serial_no: str | None = None
    install_date: date | None = None
    fidelity_level: int = Field(2, ge=1, le=4)
    ideal_cycle_time_s: float | None = Field(None, gt=0)
    rated_power_kw: float | None = Field(None, ge=0)
    model_3d_path: str | None = None
    position: Position | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class AssetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    manufacturer: str | None = None
    model: str | None = None
    serial_no: str | None = None
    install_date: date | None = None
    fidelity_level: int | None = Field(None, ge=1, le=4)
    ideal_cycle_time_s: float | None = Field(None, gt=0)
    rated_power_kw: float | None = Field(None, ge=0)
    model_3d_path: str | None = None
    position: Position | None = None
    status: AssetStatus | None = None
    attributes: dict[str, Any] | None = None


class AssetClone(BaseModel):
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)


class AssetOut(ORMModel):
    id: uuid.UUID
    line_id: uuid.UUID
    code: str
    name: str
    asset_type: str
    manufacturer: str | None
    model: str | None
    serial_no: str | None
    install_date: date | None
    ditto_thing_id: str
    aas_id: str | None
    fidelity_level: int
    ideal_cycle_time_s: float | None
    rated_power_kw: float | None
    model_3d_path: str | None
    position: dict[str, Any] | None
    status: str
    attributes: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ComponentCreate(BaseModel):
    asset_id: uuid.UUID
    code: str = Field(pattern=PART_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    component_type: str = Field(pattern=PART_CODE_PATTERN)
    health_weight: float = Field(1.0, gt=0, le=1)
    physics_model: str | None = None
    physics_params: dict[str, Any] = Field(default_factory=dict)


class ComponentOut(ORMModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    code: str
    name: str
    component_type: str
    health_weight: float
    physics_model: str | None
    physics_params: dict[str, Any]


class SensorSpec(BaseModel):
    """A sensor definition as it arrives from the simulator catalog, AASX import or clone."""

    code: str
    component_code: str | None
    metric_name: str
    name: str
    unit: str
    kind: SensorKind
    sample_rate_hz: float = 1.0
    min_valid: float | None = None
    max_valid: float | None = None
    warn_low: float | None = None
    warn_high: float | None = None
    alarm_low: float | None = None
    alarm_high: float | None = None


class ComponentSpec(BaseModel):
    code: str
    name: str
    component_type: str
    health_weight: float = 1.0
    physics_model: str | None = None
    physics_params: dict[str, Any] = Field(default_factory=dict)


class SensorOut(ORMModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    code: str
    metric_name: str
    name: str
    unit: str
    kind: str
    sample_rate_hz: float
    min_valid: float | None
    max_valid: float | None
    warn_low: float | None
    warn_high: float | None
    alarm_low: float | None
    alarm_high: float | None


class FailureModeOut(ORMModel):
    id: uuid.UUID
    asset_type: str
    code: str
    name: str
    component_type: str | None
    description: str | None
    signature: dict[str, Any]
    severity: int
