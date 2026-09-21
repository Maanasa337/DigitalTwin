"""Pydantic schemas for maintenance scheduling (M7)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.common.schemas import ORMModel

WorkOrderType = Literal["corrective", "preventive", "predictive"]
WorkOrderStatus = Literal["open", "scheduled", "in_progress", "closed", "cancelled"]
CreatedVia = Literal["ui", "voice", "chat", "auto"]
AvailabilityKind = Literal["available", "leave", "training"]
ExportFormat = Literal["csv", "json", "b2mml"]


# ── Technicians ───────────────────────────────────────────────────────


class TechnicianCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    user_id: uuid.UUID | None = None
    skills: list[str] = Field(default_factory=list)
    hourly_cost: Decimal | None = Field(None, ge=0)


class TechnicianOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    code: str
    name: str
    skills: list[str]
    hourly_cost: Decimal | None
    created_at: datetime
    updated_at: datetime


class AvailabilityCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime
    kind: AvailabilityKind = "available"

    @model_validator(mode="after")
    def _ordered(self) -> AvailabilityCreate:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class AvailabilityOut(ORMModel):
    id: uuid.UUID
    technician_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    kind: str


# ── Work orders ───────────────────────────────────────────────────────


class WorkOrderTaskSpec(BaseModel):
    sequence: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=500)


class WorkOrderTaskOut(ORMModel):
    id: uuid.UUID
    work_order_id: uuid.UUID
    sequence: int
    description: str
    done: bool
    done_at: datetime | None


class WorkOrderCreate(BaseModel):
    asset_id: uuid.UUID
    component_id: uuid.UUID | None = None
    type: WorkOrderType = "corrective"
    priority: int = Field(3, ge=1, le=5)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=4000)
    failure_mode_id: uuid.UUID | None = None
    prediction_id: uuid.UUID | None = None
    explanation_id: uuid.UUID | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    technician_id: uuid.UUID | None = None
    parts: list[dict[str, Any]] = Field(default_factory=list)
    est_duration_min: int | None = Field(None, ge=1, le=10080)
    est_cost: Decimal | None = Field(None, ge=0)
    tasks: list[WorkOrderTaskSpec] = Field(default_factory=list)
    created_via: CreatedVia = "ui"

    @model_validator(mode="after")
    def _ordered(self) -> WorkOrderCreate:
        if self.planned_start and self.planned_end and self.planned_end <= self.planned_start:
            raise ValueError("planned_end must be after planned_start")
        return self


class WorkOrderUpdate(BaseModel):
    priority: int | None = Field(None, ge=1, le=5)
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=4000)
    status: WorkOrderStatus | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    technician_id: uuid.UUID | None = None
    parts: list[dict[str, Any]] | None = None
    est_duration_min: int | None = Field(None, ge=1, le=10080)
    est_cost: Decimal | None = Field(None, ge=0)


class WorkOrderClose(BaseModel):
    outcome: str = Field(min_length=1, max_length=4000)
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    prediction_was_correct: bool | None = None
    reset_damage: bool = True


class WorkOrderOut(ORMModel):
    id: uuid.UUID
    number: int
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    type: str
    priority: int
    title: str
    description: str | None
    failure_mode_id: uuid.UUID | None
    prediction_id: uuid.UUID | None
    explanation_id: uuid.UUID | None
    status: str
    planned_start: datetime | None
    planned_end: datetime | None
    actual_start: datetime | None
    actual_end: datetime | None
    technician_id: uuid.UUID | None
    parts: list[dict[str, Any]]
    est_duration_min: int | None
    est_cost: Decimal | None
    risk_before_slot: float | None
    created_via: str
    outcome: str | None
    prediction_was_correct: bool | None
    created_at: datetime
    updated_at: datetime


class WorkOrderDetail(WorkOrderOut):
    asset_code: str | None = None
    technician_name: str | None = None
    tasks: list[WorkOrderTaskOut] = Field(default_factory=list)


class WorkOrderRiskOut(BaseModel):
    work_order_id: uuid.UUID
    planned_start: datetime | None
    risk: float
    risk_earlier: float
    risk_later: float
    shift_hours: float
    rul_point: float | None = None
    rul_low: float | None = None
    rul_high: float | None = None


# ── Schedules ─────────────────────────────────────────────────────────


class ObjectiveWeights(BaseModel):
    downtime_cost: float = Field(1.0, ge=0, le=10)
    failure_risk: float = Field(1.0, ge=0, le=10)
    energy_cost: float = Field(1.0, ge=0, le=10)


class OptimiseRequest(BaseModel):
    horizon_start: datetime
    horizon_end: datetime
    weights: ObjectiveWeights = Field(default_factory=ObjectiveWeights)
    asset_ids: list[uuid.UUID] = Field(default_factory=list)
    activate: bool = True

    @model_validator(mode="after")
    def _horizon(self) -> OptimiseRequest:
        if self.horizon_end <= self.horizon_start:
            raise ValueError("horizon_end must be after horizon_start")
        if (self.horizon_end - self.horizon_start).days > 31:
            raise ValueError("horizon cannot exceed 31 days")
        return self


class ScheduleItemOut(ORMModel):
    id: uuid.UUID
    schedule_id: uuid.UUID
    work_order_id: uuid.UUID
    technician_id: uuid.UUID | None
    starts_at: datetime
    ends_at: datetime
    risk_before: float | None
    energy_cost: Decimal | None
    manually_adjusted: bool


class ScheduleItemPatch(BaseModel):
    """A Gantt drag: new slot and/or a different technician."""

    starts_at: datetime | None = None
    ends_at: datetime | None = None
    technician_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _ordered(self) -> ScheduleItemPatch:
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class ScheduleOut(ORMModel):
    id: uuid.UUID
    created_at: datetime
    horizon_start: datetime
    horizon_end: datetime
    objective: dict[str, Any]
    solver_status: str | None
    solve_ms: int | None
    objective_value: float | None
    is_active: bool


class ScheduleDetail(ScheduleOut):
    items: list[ScheduleItemOut] = Field(default_factory=list)
    unscheduled: list[uuid.UUID] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
