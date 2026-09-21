"""Pydantic schemas for production and energy analytics (M8)."""

from __future__ import annotations

import uuid
from datetime import datetime, time
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.common.schemas import ORMModel

Scope = Literal["plant", "line", "asset"]
Period = Literal["shift", "day", "week", "month"]


class KpiDefinitionOut(ORMModel):
    code: str
    name: str
    unit: str
    formula: str
    standard_ref: str | None
    version: int


class KpiValueOut(ORMModel):
    time: datetime
    period: str
    scope: str
    scope_id: uuid.UUID
    kpi_code: str
    value: float
    inputs: dict[str, Any] | None
    formula_version: int


class KpiSeriesOut(BaseModel):
    kpi_code: str
    name: str
    unit: str
    formula: str
    points: list[dict[str, Any]] = Field(default_factory=list)


class OeeOut(BaseModel):
    scope: str
    scope_id: uuid.UUID
    period: str
    from_: datetime = Field(alias="from")
    to: datetime
    oee: float
    availability: float
    performance: float
    quality: float
    inputs: dict[str, Any] = Field(default_factory=dict)
    trend: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ReliabilityOut(BaseModel):
    scope_id: uuid.UUID
    mtbf_h: float
    mttr_h: float
    breakdowns: int
    repairs: int


class DowntimeParetoOut(BaseModel):
    scope: str
    scope_id: uuid.UUID
    total_seconds: float
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ProductionPlanOut(BaseModel):
    scope_id: uuid.UUID
    planned: int
    actual: int
    good: int
    reject: int
    attainment: float
    cycle_time_histogram: list[dict[str, Any]] = Field(default_factory=list)


# ── Energy ────────────────────────────────────────────────────────────


class EnergySummaryOut(BaseModel):
    scope: str
    scope_id: uuid.UUID
    from_: datetime = Field(alias="from")
    to: datetime
    energy_kwh: float
    cost: float
    currency: str
    co2_kg: float
    peak_demand_kw: float
    idle_energy_kwh: float
    idle_energy_share: float
    energy_per_unit: float | None
    breakdown: list[dict[str, Any]] = Field(default_factory=list)
    intensity_trend: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class EnergyAnomalyOut(BaseModel):
    time: datetime
    scope_id: uuid.UUID
    energy_kwh: float
    expected_kwh: float
    units: float
    sigma: float
    health_index: float | None = None


class BaselineCreate(BaseModel):
    scope: Scope = "asset"
    scope_id: uuid.UUID
    period_start: datetime
    period_end: datetime

    @model_validator(mode="after")
    def _period(self) -> BaselineCreate:
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be after period_start")
        return self


class BaselineOut(ORMModel):
    id: uuid.UUID
    scope: str
    scope_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    intercept_kwh: float
    slope_kwh_per_unit: float
    r2: float | None
    created_at: datetime


# ── Shifts and tariffs ────────────────────────────────────────────────


class ShiftCreate(BaseModel):
    plant_id: uuid.UUID
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=100)
    starts_local: time
    ends_local: time
    days_of_week: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def _days(self) -> ShiftCreate:
        if any(day < 0 or day > 6 for day in self.days_of_week):
            raise ValueError("days_of_week entries must be 0 (Monday) to 6 (Sunday)")
        return self


class ShiftOut(ORMModel):
    id: uuid.UUID
    plant_id: uuid.UUID
    code: str
    name: str
    starts_local: time
    ends_local: time
    days_of_week: list[int]


class TariffCreate(BaseModel):
    plant_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    starts_local: time
    ends_local: time
    rate_per_kwh: Decimal = Field(ge=0)
    days_of_week: list[int] = Field(min_length=1)


class TariffOut(ORMModel):
    id: uuid.UUID
    plant_id: uuid.UUID
    name: str
    starts_local: time
    ends_local: time
    rate_per_kwh: Decimal
    days_of_week: list[int]
