"""maintenance: technicians, availability, work orders, tasks, schedules, schedule items

Revision ID: 0007_maintenance
Revises: 0006_xai
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0007_maintenance"
down_revision: str | None = "0006_xai"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSTZ = sa.DateTime(timezone=True)
ACTIVE = sa.text("deleted_at IS NULL")


def _pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _timestamps(soft_delete: bool = True) -> list[sa.Column]:
    cols = [
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.func.now(), nullable=False),
    ]
    if soft_delete:
        cols.append(sa.Column("deleted_at", TSTZ, nullable=True))
    return cols


def upgrade() -> None:
    # ── technicians ───────────────────────────────────────────────────
    op.create_table(
        "technicians",
        _pk(),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("skills", pg.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("hourly_cost", sa.Numeric(10, 2), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_technicians_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_technicians"),
    )
    op.create_index("technicians_code_uq", "technicians", ["code"], unique=True, postgresql_where=ACTIVE)

    # ── technician_availability ───────────────────────────────────────
    op.create_table(
        "technician_availability",
        _pk(),
        sa.Column("technician_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", TSTZ, nullable=False),
        sa.Column("ends_at", TSTZ, nullable=False),
        sa.Column("kind", sa.String(), server_default="available", nullable=False),
        sa.CheckConstraint("kind in ('available','leave','training')", name="ck_technician_availability_kind"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_technician_availability_range"),
        sa.ForeignKeyConstraint(
            ["technician_id"], ["technicians.id"], name="fk_technician_availability_technician_id_technicians"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_technician_availability"),
    )
    op.create_index(
        "ix_technician_availability_technician_id_starts_at",
        "technician_availability",
        ["technician_id", "starts_at"],
    )

    # ── work_orders ───────────────────────────────────────────────────
    op.create_table(
        "work_orders",
        _pk(),
        sa.Column("number", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("component_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), server_default="3", nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("failure_mode_id", sa.Uuid(), nullable=True),
        sa.Column("prediction_id", sa.Uuid(), nullable=True),
        sa.Column("explanation_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(), server_default="open", nullable=False),
        sa.Column("planned_start", TSTZ, nullable=True),
        sa.Column("planned_end", TSTZ, nullable=True),
        sa.Column("actual_start", TSTZ, nullable=True),
        sa.Column("actual_end", TSTZ, nullable=True),
        sa.Column("technician_id", sa.Uuid(), nullable=True),
        sa.Column("parts", pg.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("est_duration_min", sa.Integer(), nullable=True),
        sa.Column("est_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("risk_before_slot", sa.Float(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_via", sa.String(), server_default="ui", nullable=False),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("prediction_was_correct", sa.Boolean(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("type in ('corrective','preventive','predictive')", name="ck_work_orders_type"),
        sa.CheckConstraint("priority between 1 and 5", name="ck_work_orders_priority"),
        sa.CheckConstraint(
            "status in ('open','scheduled','in_progress','closed','cancelled')", name="ck_work_orders_status"
        ),
        sa.CheckConstraint("created_via in ('ui','voice','chat','auto')", name="ck_work_orders_created_via"),
        sa.CheckConstraint(
            "planned_end IS NULL OR planned_start IS NULL OR planned_end > planned_start",
            name="ck_work_orders_planned_range",
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_work_orders_asset_id_assets"),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], name="fk_work_orders_component_id_components"),
        sa.ForeignKeyConstraint(
            ["failure_mode_id"], ["failure_modes.id"], name="fk_work_orders_failure_mode_id_failure_modes"
        ),
        sa.ForeignKeyConstraint(
            ["explanation_id"], ["explanations.id"], name="fk_work_orders_explanation_id_explanations"
        ),
        sa.ForeignKeyConstraint(["technician_id"], ["technicians.id"], name="fk_work_orders_technician_id_technicians"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_work_orders_created_by_users"),
        sa.PrimaryKeyConstraint("id", name="pk_work_orders"),
    )
    op.create_index("work_orders_number_uq", "work_orders", ["number"], unique=True)
    op.create_index("ix_work_orders_asset_id_status", "work_orders", ["asset_id", "status"])
    op.create_index("ix_work_orders_planned_start", "work_orders", ["planned_start"])
    op.create_index("ix_work_orders_technician_id", "work_orders", ["technician_id"])
    # The auto-creation rule is "one open order per asset and failure mode"; the index enforces it
    # so two concurrent inference workers cannot both raise the same order.
    op.create_index(
        "work_orders_open_mode_uq",
        "work_orders",
        ["asset_id", "failure_mode_id"],
        unique=True,
        postgresql_where=sa.text(
            "deleted_at IS NULL AND failure_mode_id IS NOT NULL "
            "AND status in ('open','scheduled','in_progress') AND created_via = 'auto'"
        ),
    )

    # ── work_order_tasks ──────────────────────────────────────────────
    op.create_table(
        "work_order_tasks",
        _pk(),
        sa.Column("work_order_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("done", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("done_at", TSTZ, nullable=True),
        sa.ForeignKeyConstraint(
            ["work_order_id"], ["work_orders.id"], name="fk_work_order_tasks_work_order_id_work_orders"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_work_order_tasks"),
    )
    op.create_index("work_order_tasks_sequence_uq", "work_order_tasks", ["work_order_id", "sequence"], unique=True)

    # ── schedules ─────────────────────────────────────────────────────
    op.create_table(
        "schedules",
        _pk(),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("horizon_start", TSTZ, nullable=False),
        sa.Column("horizon_end", TSTZ, nullable=False),
        sa.Column("objective", pg.JSONB(), nullable=False),
        sa.Column("solver_status", sa.String(), nullable=True),
        sa.Column("solve_ms", sa.Integer(), nullable=True),
        sa.Column("objective_value", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint("horizon_end > horizon_start", name="ck_schedules_horizon"),
        sa.PrimaryKeyConstraint("id", name="pk_schedules"),
    )
    # Exactly one active schedule: the Gantt and the risk overlay both read "the" current plan.
    op.create_index(
        "schedules_active_uq", "schedules", [sa.text("(true)")], unique=True, postgresql_where=sa.text("is_active")
    )

    # ── schedule_items ────────────────────────────────────────────────
    op.create_table(
        "schedule_items",
        _pk(),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("work_order_id", sa.Uuid(), nullable=False),
        sa.Column("technician_id", sa.Uuid(), nullable=True),
        sa.Column("starts_at", TSTZ, nullable=False),
        sa.Column("ends_at", TSTZ, nullable=False),
        sa.Column("risk_before", sa.Float(), nullable=True),
        sa.Column("energy_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("manually_adjusted", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_schedule_items_range"),
        sa.ForeignKeyConstraint(
            ["schedule_id"], ["schedules.id"], ondelete="CASCADE", name="fk_schedule_items_schedule_id_schedules"
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"], ["work_orders.id"], name="fk_schedule_items_work_order_id_work_orders"
        ),
        sa.ForeignKeyConstraint(
            ["technician_id"], ["technicians.id"], name="fk_schedule_items_technician_id_technicians"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_items"),
    )
    op.create_index("ix_schedule_items_schedule_id", "schedule_items", ["schedule_id"])
    op.create_index("schedule_items_order_uq", "schedule_items", ["schedule_id", "work_order_id"], unique=True)


def downgrade() -> None:
    op.drop_table("schedule_items")
    op.drop_table("schedules")
    op.drop_table("work_order_tasks")
    op.drop_table("work_orders")
    op.drop_table("technician_availability")
    op.drop_table("technicians")
