"""analytics: shifts, tariffs, kpi definitions and values, energy baselines

Revision ID: 0008_analytics
Revises: 0007_maintenance
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0008_analytics"
down_revision: str | None = "0007_maintenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSTZ = sa.DateTime(timezone=True)
ACTIVE = sa.text("deleted_at IS NULL")

# Seeded with the definitions the UI shows on hover (FR-PA-06). Kept in the migration rather than a
# seed script because kpi_values.kpi_code is a foreign key onto this table.
KPI_DEFINITIONS = [
    ("oee", "Overall Equipment Effectiveness", "%", "Availability * Performance * Quality", "ISO 22400-2 §6.4"),
    ("availability", "Availability", "%", "Run time / Planned production time", "ISO 22400-2 §6.4.1"),
    (
        "performance",
        "Performance",
        "%",
        "(Ideal cycle time * Total count) / Run time",
        "ISO 22400-2 §6.4.2",
    ),
    ("quality", "Quality", "%", "Good count / Total count", "ISO 22400-2 §6.4.3"),
    ("mtbf", "Mean Time Between Failures", "h", "Total run time / Number of breakdowns", "ISO 22400-2 §6.2"),
    ("mttr", "Mean Time To Repair", "h", "Total repair time / Number of repairs", "ISO 22400-2 §6.3"),
    ("energy_per_unit", "Energy per unit", "kWh/unit", "Total energy / Good count", "ISO 50001"),
    ("idle_energy_share", "Idle energy share", "%", "Energy while IDLE / Total energy", "ISO 50001"),
    ("peak_demand", "Peak demand", "kW", "Maximum power draw in the period", "ISO 50001"),
]


def _pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", TSTZ, nullable=True),
    ]


def upgrade() -> None:
    # ── shifts ────────────────────────────────────────────────────────
    op.create_table(
        "shifts",
        _pk(),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("starts_local", sa.Time(), nullable=False),
        sa.Column("ends_local", sa.Time(), nullable=False),
        sa.Column("days_of_week", pg.ARRAY(sa.Integer()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], name="fk_shifts_plant_id_plants"),
        sa.PrimaryKeyConstraint("id", name="pk_shifts"),
    )
    op.create_index("shifts_code_uq", "shifts", ["plant_id", "code"], unique=True, postgresql_where=ACTIVE)

    # ── tariffs ───────────────────────────────────────────────────────
    op.create_table(
        "tariffs",
        _pk(),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("starts_local", sa.Time(), nullable=False),
        sa.Column("ends_local", sa.Time(), nullable=False),
        sa.Column("rate_per_kwh", sa.Numeric(10, 4), nullable=False),
        sa.Column("days_of_week", pg.ARRAY(sa.Integer()), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("rate_per_kwh >= 0", name="ck_tariffs_rate"),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], name="fk_tariffs_plant_id_plants"),
        sa.PrimaryKeyConstraint("id", name="pk_tariffs"),
    )
    op.create_index("ix_tariffs_plant_id", "tariffs", ["plant_id"], postgresql_where=ACTIVE)

    # ── kpi_definitions ───────────────────────────────────────────────
    op.create_table(
        "kpi_definitions",
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("standard_ref", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_kpi_definitions"),
    )
    op.bulk_insert(
        sa.table(
            "kpi_definitions",
            sa.column("code", sa.String),
            sa.column("name", sa.String),
            sa.column("unit", sa.String),
            sa.column("formula", sa.Text),
            sa.column("standard_ref", sa.String),
        ),
        [
            {"code": code, "name": name, "unit": unit, "formula": formula, "standard_ref": ref}
            for code, name, unit, formula, ref in KPI_DEFINITIONS
        ],
    )

    # ── kpi_values hypertable ─────────────────────────────────────────
    op.create_table(
        "kpi_values",
        sa.Column("time", TSTZ, nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("kpi_code", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("inputs", pg.JSONB(), nullable=True),
        sa.Column("formula_version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("period in ('shift','day','week','month')", name="ck_kpi_values_period"),
        sa.CheckConstraint("scope in ('plant','line','asset')", name="ck_kpi_values_scope"),
        sa.ForeignKeyConstraint(["kpi_code"], ["kpi_definitions.code"], name="fk_kpi_values_kpi_code_kpi_definitions"),
    )
    op.execute("SELECT create_hypertable('kpi_values','time', chunk_time_interval => interval '30 days')")
    # The rollup is re-run for a period that is still open, so it must upsert rather than duplicate.
    op.create_index("kpi_values_uq", "kpi_values", ["time", "period", "scope", "scope_id", "kpi_code"], unique=True)
    op.create_index(
        "ix_kpi_values_scope_id_kpi_code_time", "kpi_values", ["scope_id", "kpi_code", sa.text("time DESC")]
    )

    # ── energy_baselines ──────────────────────────────────────────────
    op.create_table(
        "energy_baselines",
        _pk(),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", TSTZ, nullable=False),
        sa.Column("period_end", TSTZ, nullable=False),
        sa.Column("intercept_kwh", sa.Float(), nullable=False),
        sa.Column("slope_kwh_per_unit", sa.Float(), nullable=False),
        sa.Column("r2", sa.Float(), nullable=True),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("scope in ('plant','line','asset')", name="ck_energy_baselines_scope"),
        sa.CheckConstraint("period_end > period_start", name="ck_energy_baselines_period"),
        sa.PrimaryKeyConstraint("id", name="pk_energy_baselines"),
    )
    op.create_index(
        "ix_energy_baselines_scope_id_created_at", "energy_baselines", ["scope_id", sa.text("created_at DESC")]
    )


def downgrade() -> None:
    op.drop_table("energy_baselines")
    op.execute("DROP TABLE kpi_values CASCADE")
    op.drop_table("kpi_definitions")
    op.drop_table("tariffs")
    op.drop_table("shifts")
