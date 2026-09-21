import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, SmallInteger, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, PKMixin, SoftDeleteMixin, TimestampMixin

ASSET_TYPES = ("cnc_mill", "compressor", "conveyor", "hydraulic_press", "injection_moulder", "other")
ASSET_STATUSES = ("RUNNING", "IDLE", "DOWN", "MAINTENANCE", "UNKNOWN")
SENSOR_KINDS = (
    "vibration", "temperature", "current", "voltage", "power", "pressure",
    "flow", "speed", "torque", "position", "count", "other",
)  # fmt: skip

ACTIVE = text("deleted_at IS NULL")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(v) for v in values)})"


class Plant(PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "plants"
    __table_args__ = (Index("plants_code_uq", "code", unique=True, postgresql_where=ACTIVE),)

    code: Mapped[str]
    name: Mapped[str]
    timezone: Mapped[str] = mapped_column(server_default="Asia/Kolkata")
    grid_emission_factor_kg_per_kwh: Mapped[Decimal] = mapped_column(Numeric(8, 4), server_default="0.716")
    currency: Mapped[str] = mapped_column(server_default="INR")


class Line(PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "lines"
    __table_args__ = (Index("lines_code_uq", "plant_id", "code", unique=True, postgresql_where=ACTIVE),)

    plant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plants.id"))
    code: Mapped[str]
    name: Mapped[str]
    sequence: Mapped[int] = mapped_column(server_default="0")


class Asset(PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        Index("assets_code_uq", "code", unique=True, postgresql_where=ACTIVE),
        CheckConstraint(_in("asset_type", ASSET_TYPES), name="asset_type"),
        CheckConstraint(_in("status", ASSET_STATUSES), name="status"),
        CheckConstraint("fidelity_level between 1 and 4", name="fidelity_level"),
    )

    line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lines.id"), index=True)
    code: Mapped[str]
    name: Mapped[str]
    asset_type: Mapped[str]
    manufacturer: Mapped[str | None]
    model: Mapped[str | None]
    serial_no: Mapped[str | None]
    install_date: Mapped[date | None]
    ditto_thing_id: Mapped[str]
    aas_id: Mapped[str | None]
    fidelity_level: Mapped[int] = mapped_column(SmallInteger, server_default="2")
    ideal_cycle_time_s: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    rated_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    model_3d_path: Mapped[str | None]
    position: Mapped[dict[str, Any] | None]
    status: Mapped[str] = mapped_column(server_default="RUNNING")
    attributes: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))


class Component(PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "components"
    __table_args__ = (Index("components_code_uq", "asset_id", "code", unique=True, postgresql_where=ACTIVE),)

    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"))
    code: Mapped[str]
    name: Mapped[str]
    component_type: Mapped[str]
    health_weight: Mapped[Decimal] = mapped_column(Numeric(4, 3), server_default="1.0")
    physics_model: Mapped[str | None]
    physics_params: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))


class Sensor(PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "sensors"
    __table_args__ = (
        Index("sensors_metric_uq", "asset_id", "metric_name", unique=True, postgresql_where=ACTIVE),
        CheckConstraint(_in("kind", SENSOR_KINDS), name="kind"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"))
    component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("components.id"), index=True)
    code: Mapped[str]
    metric_name: Mapped[str]
    name: Mapped[str]
    unit: Mapped[str]
    kind: Mapped[str]
    sample_rate_hz: Mapped[Decimal] = mapped_column(Numeric(10, 3), server_default="1")
    min_valid: Mapped[Decimal | None] = mapped_column(Numeric)
    max_valid: Mapped[Decimal | None] = mapped_column(Numeric)
    warn_low: Mapped[Decimal | None] = mapped_column(Numeric)
    warn_high: Mapped[Decimal | None] = mapped_column(Numeric)
    alarm_low: Mapped[Decimal | None] = mapped_column(Numeric)
    alarm_high: Mapped[Decimal | None] = mapped_column(Numeric)
    adaptive_sigma: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    # Set by M6 explanation feedback naming this sensor; expires so a stale flag cannot mute confidence forever.
    quality_flag: Mapped[str | None]
    quality_flag_until: Mapped[datetime | None]


class AasSubmodel(PKMixin, TimestampMixin, Base):
    __tablename__ = "aas_submodels"
    __table_args__ = (Index("aas_submodels_uq", "asset_id", "id_short", unique=True),)

    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"))
    semantic_id: Mapped[str]
    id_short: Mapped[str]
    version: Mapped[str] = mapped_column(server_default="1.0")
    content: Mapped[dict[str, Any]]


class FailureMode(PKMixin, TimestampMixin, Base):
    __tablename__ = "failure_modes"
    __table_args__ = (
        Index("failure_modes_uq", "asset_type", "code", unique=True),
        CheckConstraint("severity between 1 and 4", name="severity"),
    )

    asset_type: Mapped[str]
    code: Mapped[str]
    name: Mapped[str]
    component_type: Mapped[str | None]
    description: Mapped[str | None]
    signature: Mapped[dict[str, Any]]
    severity: Mapped[int] = mapped_column(SmallInteger, server_default="3")
