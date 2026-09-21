"""Pydantic schemas for telemetry queries, alarms and alarm rules (M3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Enums ─────────────────────────────────────────────────────────────


class AggLevel(StrEnum):
    RAW = "raw"
    ONE_MIN = "1m"
    ONE_HOUR = "1h"


class AlarmSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    SERIOUS = "serious"
    CRITICAL = "critical"


class AlarmStatus(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    SHELVED = "shelved"
    CLEARED = "cleared"


class AlarmRuleKind(StrEnum):
    THRESHOLD = "threshold"
    ADAPTIVE = "adaptive"
    ML_ANOMALY = "ml_anomaly"
    ENERGY_INTENSITY = "energy_intensity"


class AlarmActionType(StrEnum):
    ACK = "ack"
    ASSIGN = "assign"
    COMMENT = "comment"
    SHELVE = "shelve"
    UNSHELVE = "unshelve"
    CLEAR = "clear"


# ── Telemetry ─────────────────────────────────────────────────────────


class TelemetryPoint(BaseModel):
    time: datetime
    value: float
    quality: int = 192


class TelemetryAggPoint(BaseModel):
    bucket: datetime
    avg: float | None = None
    min: float | None = None
    max: float | None = None
    std: float | None = None
    n: int = 0


class TelemetrySeries(BaseModel):
    sensor_id: str
    metric_name: str
    unit: str
    points: list[TelemetryPoint | TelemetryAggPoint]


class TelemetryLatestValue(BaseModel):
    sensor_id: str
    metric_name: str
    name: str
    unit: str
    value: float | None
    quality: int
    time: datetime | None


class TelemetryLatestResponse(BaseModel):
    asset_code: str
    values: list[TelemetryLatestValue]


# ── Alarm rules ───────────────────────────────────────────────────────


class AlarmRuleCreate(BaseModel):
    sensor_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    kind: AlarmRuleKind
    params: dict[str, Any]
    severity: AlarmSeverity
    enabled: bool = True


class AlarmRuleUpdate(BaseModel):
    params: dict[str, Any] | None = None
    severity: AlarmSeverity | None = None
    enabled: bool | None = None


class AlarmRuleOut(BaseModel):
    id: uuid.UUID
    sensor_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    kind: AlarmRuleKind
    params: dict[str, Any]
    severity: AlarmSeverity
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Alarms ────────────────────────────────────────────────────────────


class AlarmOut(BaseModel):
    id: uuid.UUID
    raised_at: datetime
    cleared_at: datetime | None
    asset_id: uuid.UUID
    sensor_id: uuid.UUID | None
    rule_id: uuid.UUID | None
    severity: AlarmSeverity
    title: str
    message: str
    value: float | None
    threshold: float | None
    prediction_id: uuid.UUID | None
    status: AlarmStatus
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
    assigned_to: uuid.UUID | None
    shelved_until: datetime | None

    model_config = {"from_attributes": True}


class AlarmActionCreate(BaseModel):
    action: AlarmActionType
    note: str | None = None
    assigned_to: uuid.UUID | None = None
    shelve_hours: float | None = Field(None, ge=0.25, le=168)


class AlarmActionOut(BaseModel):
    id: uuid.UUID
    alarm_id: uuid.UUID
    at: datetime
    actor_id: uuid.UUID | None
    action: AlarmActionType
    note: str | None

    model_config = {"from_attributes": True}
