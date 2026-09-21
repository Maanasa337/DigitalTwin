"""ORM models for telemetry, events, and alarms (M3).

Telemetry and event tables are append-only and time-keyed, so they use no mixins.
Alarm-related master tables use PKMixin.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Numeric, SmallInteger, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, PKMixin, SoftDeleteMixin, TimestampMixin

ALARM_SEVERITIES = ("info", "warning", "serious", "critical")
ALARM_STATUSES = ("active", "acknowledged", "shelved", "cleared")
ALARM_RULE_KINDS = ("threshold", "adaptive", "ml_anomaly", "energy_intensity")
ALARM_ACTION_TYPES = ("ack", "assign", "comment", "shelve", "unshelve", "clear")
ASSET_STATES = ("RUNNING", "IDLE", "DOWN", "MAINTENANCE", "UNKNOWN")

_in = lambda col, vals: f"{col} in ({', '.join(repr(v) for v in vals)})"  # noqa: E731


# ── Append-only telemetry ─────────────────────────────────────────────


class Telemetry(Base):
    """Narrow telemetry: one row per (time, sensor_id)."""

    __tablename__ = "telemetry"

    __table_args__ = (Index("ix_telemetry_sensor_id_time", "sensor_id", text("time DESC")),)

    time: Mapped[datetime] = mapped_column(primary_key=True)
    sensor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sensors.id"), primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    quality: Mapped[int] = mapped_column(SmallInteger, server_default="192")


class Waveform(Base):
    __tablename__ = "waveforms"

    time: Mapped[datetime] = mapped_column(primary_key=True)
    sensor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sensors.id"), primary_key=True)
    sample_rate_hz: Mapped[int]
    n_samples: Mapped[int]
    samples: Mapped[bytes]
    features: Mapped[dict[str, Any] | None]


class EnergyReading(Base):
    __tablename__ = "energy_readings"
    __table_args__ = (Index("ix_energy_readings_asset_id_time", "asset_id", text("time DESC")),)

    time: Mapped[datetime] = mapped_column(primary_key=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    power_kw: Mapped[float] = mapped_column(Float)
    energy_kwh: Mapped[float] = mapped_column(Float)
    power_factor: Mapped[float | None] = mapped_column(Float)
    current_a: Mapped[float | None] = mapped_column(Float)
    voltage_v: Mapped[float | None] = mapped_column(Float)
    # A money rate, so Numeric like every other currency column; the migration already had it
    # this way and only the model said Float.
    tariff_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))


class ProductionCount(Base):
    __tablename__ = "production_counts"

    time: Mapped[datetime] = mapped_column(primary_key=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    shift_id: Mapped[uuid.UUID | None]
    good_count: Mapped[int] = mapped_column(server_default="0")
    reject_count: Mapped[int] = mapped_column(server_default="0")
    cycle_time_s: Mapped[float | None] = mapped_column(Float)
    planned: Mapped[bool] = mapped_column(Boolean, server_default="true")


class AssetStateEvent(Base):
    __tablename__ = "asset_state_events"
    __table_args__ = (CheckConstraint(_in("state", ASSET_STATES), name="state"),)

    time: Mapped[datetime] = mapped_column(primary_key=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    state: Mapped[str]
    cause_code: Mapped[str | None]
    duration_s: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(server_default="simulator")


# ── Alarm rules and alarms ────────────────────────────────────────────


class AlarmRule(PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "alarm_rules"
    __table_args__ = (
        CheckConstraint(_in("kind", ALARM_RULE_KINDS), name="kind"),
        CheckConstraint(_in("severity", ALARM_SEVERITIES), name="severity"),
    )

    sensor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sensors.id"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id"))
    kind: Mapped[str]
    params: Mapped[dict[str, Any]]
    severity: Mapped[str]
    enabled: Mapped[bool] = mapped_column(server_default="true")


class Alarm(PKMixin, Base):
    __tablename__ = "alarms"
    __table_args__ = (
        CheckConstraint(_in("severity", ALARM_SEVERITIES), name="severity"),
        CheckConstraint(_in("status", ALARM_STATUSES), name="status"),
        Index("ix_alarms_asset_id_status_raised_at", "asset_id", "status", text("raised_at DESC")),
    )

    raised_at: Mapped[datetime] = mapped_column(server_default=func.now())
    cleared_at: Mapped[datetime | None]
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"))
    sensor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sensors.id"))
    rule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("alarm_rules.id"))
    severity: Mapped[str]
    title: Mapped[str]
    message: Mapped[str]
    value: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    prediction_id: Mapped[uuid.UUID | None]
    status: Mapped[str] = mapped_column(server_default="active")
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None]
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    shelved_until: Mapped[datetime | None]


class AlarmAction(PKMixin, Base):
    __tablename__ = "alarm_actions"
    __table_args__ = (CheckConstraint(_in("action", ALARM_ACTION_TYPES), name="action"),)

    alarm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alarms.id"))
    at: Mapped[datetime] = mapped_column(server_default=func.now())
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str]
    note: Mapped[str | None]
