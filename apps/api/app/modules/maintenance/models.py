"""ORM models for maintenance scheduling (M7): technicians, work orders, schedules."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, PKMixin, SoftDeleteMixin, TimestampMixin

WORK_ORDER_TYPES = ("corrective", "preventive", "predictive")
WORK_ORDER_STATUSES = ("open", "scheduled", "in_progress", "closed", "cancelled")
CREATED_VIA = ("ui", "voice", "chat", "auto")
AVAILABILITY_KINDS = ("available", "leave", "training")
OPEN_STATUSES = ("open", "scheduled", "in_progress")

ACTIVE = text("deleted_at IS NULL")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(v) for v in values)})"


class Technician(PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "technicians"
    __table_args__ = (Index("technicians_code_uq", "code", unique=True, postgresql_where=ACTIVE),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    code: Mapped[str]
    name: Mapped[str]
    skills: Mapped[list[str]] = mapped_column(server_default=text("'{}'"))
    hourly_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))


class TechnicianAvailability(PKMixin, Base):
    __tablename__ = "technician_availability"
    __table_args__ = (
        CheckConstraint(_in("kind", AVAILABILITY_KINDS), name="kind"),
        CheckConstraint("ends_at > starts_at", name="range"),
        Index("ix_technician_availability_technician_id_starts_at", "technician_id", "starts_at"),
    )

    technician_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("technicians.id"))
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    kind: Mapped[str] = mapped_column(server_default="available")


class WorkOrder(PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        CheckConstraint(_in("type", WORK_ORDER_TYPES), name="type"),
        CheckConstraint("priority between 1 and 5", name="priority"),
        CheckConstraint(_in("status", WORK_ORDER_STATUSES), name="status"),
        CheckConstraint(_in("created_via", CREATED_VIA), name="created_via"),
        CheckConstraint(
            "planned_end IS NULL OR planned_start IS NULL OR planned_end > planned_start",
            name="planned_range",
        ),
        Index("work_orders_number_uq", "number", unique=True),
        # One open auto-raised order per asset and failure mode, so two concurrent inference
        # workers cannot both raise it.
        Index(
            "work_orders_open_mode_uq",
            "asset_id",
            "failure_mode_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND failure_mode_id IS NOT NULL "
                "AND status in ('open','scheduled','in_progress') AND created_via = 'auto'"
            ),
        ),
        Index("ix_work_orders_asset_id_status", "asset_id", "status"),
        Index("ix_work_orders_planned_start", "planned_start"),
        Index("ix_work_orders_technician_id", "technician_id"),
    )

    number: Mapped[int] = mapped_column(Identity(always=False))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"))
    component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("components.id"))
    type: Mapped[str]
    priority: Mapped[int] = mapped_column(SmallInteger, server_default="3")
    title: Mapped[str]
    description: Mapped[str | None] = mapped_column(Text)
    failure_mode_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("failure_modes.id"))
    prediction_id: Mapped[uuid.UUID | None]
    explanation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("explanations.id"))
    status: Mapped[str] = mapped_column(server_default="open")
    planned_start: Mapped[datetime | None]
    planned_end: Mapped[datetime | None]
    actual_start: Mapped[datetime | None]
    actual_end: Mapped[datetime | None]
    technician_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("technicians.id"))
    parts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    est_duration_min: Mapped[int | None]
    est_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    risk_before_slot: Mapped[float | None] = mapped_column(Float)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_via: Mapped[str] = mapped_column(server_default="ui")
    outcome: Mapped[str | None] = mapped_column(Text)
    prediction_was_correct: Mapped[bool | None] = mapped_column(Boolean)


class WorkOrderTask(PKMixin, Base):
    __tablename__ = "work_order_tasks"
    __table_args__ = (Index("work_order_tasks_sequence_uq", "work_order_id", "sequence", unique=True),)

    work_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_orders.id"))
    sequence: Mapped[int]
    description: Mapped[str] = mapped_column(Text)
    done: Mapped[bool] = mapped_column(Boolean, server_default="false")
    done_at: Mapped[datetime | None]


class Schedule(PKMixin, Base):
    __tablename__ = "schedules"
    __table_args__ = (
        CheckConstraint("horizon_end > horizon_start", name="horizon"),
        # Exactly one active plan at a time.
        Index("schedules_active_uq", text("(true)"), unique=True, postgresql_where=text("is_active")),
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    horizon_start: Mapped[datetime]
    horizon_end: Mapped[datetime]
    objective: Mapped[dict[str, Any]]
    solver_status: Mapped[str | None]
    solve_ms: Mapped[int | None]
    objective_value: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="false")


class ScheduleItem(PKMixin, Base):
    __tablename__ = "schedule_items"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="range"),
        Index("ix_schedule_items_schedule_id", "schedule_id"),
        Index("schedule_items_order_uq", "schedule_id", "work_order_id", unique=True),
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"))
    work_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_orders.id"))
    technician_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("technicians.id"))
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    risk_before: Mapped[float | None] = mapped_column(Float)
    energy_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    manually_adjusted: Mapped[bool] = mapped_column(Boolean, server_default="false")
