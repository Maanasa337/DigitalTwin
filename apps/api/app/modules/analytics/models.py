"""ORM models for production and energy analytics (M8)."""

import uuid
from datetime import datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, Numeric, Text, Time, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, PKMixin, SoftDeleteMixin, TimestampMixin

KPI_PERIODS = ("shift", "day", "week", "month")
KPI_SCOPES = ("plant", "line", "asset")

ACTIVE = text("deleted_at IS NULL")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(v) for v in values)})"


class Shift(PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "shifts"
    __table_args__ = (Index("shifts_code_uq", "plant_id", "code", unique=True, postgresql_where=ACTIVE),)

    plant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plants.id"))
    code: Mapped[str]
    name: Mapped[str]
    starts_local: Mapped[time] = mapped_column(Time)
    ends_local: Mapped[time] = mapped_column(Time)
    days_of_week: Mapped[list[int]] = mapped_column(ARRAY(Integer))


class Tariff(PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tariffs"
    __table_args__ = (
        CheckConstraint("rate_per_kwh >= 0", name="rate"),
        Index("ix_tariffs_plant_id", "plant_id", postgresql_where=ACTIVE),
    )

    plant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plants.id"))
    name: Mapped[str]
    starts_local: Mapped[time] = mapped_column(Time)
    ends_local: Mapped[time] = mapped_column(Time)
    rate_per_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    days_of_week: Mapped[list[int]] = mapped_column(ARRAY(Integer))


class KpiDefinition(Base):
    __tablename__ = "kpi_definitions"

    code: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    unit: Mapped[str]
    formula: Mapped[str] = mapped_column(Text)
    standard_ref: Mapped[str | None]
    version: Mapped[int] = mapped_column(server_default="1")


class KpiValue(Base):
    """Append-only, time-keyed: the natural key is (time, period, scope, scope_id, kpi_code)."""

    __tablename__ = "kpi_values"
    __table_args__ = (
        CheckConstraint(_in("period", KPI_PERIODS), name="period"),
        CheckConstraint(_in("scope", KPI_SCOPES), name="scope"),
        Index("ix_kpi_values_scope_id_kpi_code_time", "scope_id", "kpi_code", text("time DESC")),
        # The rollup re-runs for a period that is still open, so it upserts on this key.
        Index("kpi_values_uq", "time", "period", "scope", "scope_id", "kpi_code", unique=True),
    )

    time: Mapped[datetime] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(primary_key=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    kpi_code: Mapped[str] = mapped_column(ForeignKey("kpi_definitions.code"), primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    inputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    formula_version: Mapped[int] = mapped_column(server_default="1")


class EnergyBaseline(PKMixin, Base):
    __tablename__ = "energy_baselines"
    __table_args__ = (
        CheckConstraint(_in("scope", KPI_SCOPES), name="scope"),
        CheckConstraint("period_end > period_start", name="period"),
        Index("ix_energy_baselines_scope_id_created_at", "scope_id", text("created_at DESC")),
    )

    scope: Mapped[str]
    scope_id: Mapped[uuid.UUID]
    period_start: Mapped[datetime]
    period_end: Mapped[datetime]
    intercept_kwh: Mapped[float] = mapped_column(Float)
    slope_kwh_per_unit: Mapped[float] = mapped_column(Float)
    r2: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
