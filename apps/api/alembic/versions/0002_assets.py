"""assets: plants, lines, assets, components, sensors, aas_submodels, failure_modes

Revision ID: 0002_assets
Revises: 0001_core
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002_assets"
down_revision: str | None = "0001_core"
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
    op.create_table(
        "plants",
        _pk(),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), server_default="Asia/Kolkata", nullable=False),
        sa.Column("grid_emission_factor_kg_per_kwh", sa.Numeric(8, 4), server_default="0.716", nullable=False),
        sa.Column("currency", sa.String(), server_default="INR", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_plants"),
    )
    op.create_index("plants_code_uq", "plants", ["code"], unique=True, postgresql_where=ACTIVE)

    op.create_table(
        "lines",
        _pk(),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], name="fk_lines_plant_id_plants"),
        sa.PrimaryKeyConstraint("id", name="pk_lines"),
    )
    op.create_index("lines_code_uq", "lines", ["plant_id", "code"], unique=True, postgresql_where=ACTIVE)

    op.create_table(
        "assets",
        _pk(),
        sa.Column("line_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("manufacturer", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("serial_no", sa.String(), nullable=True),
        sa.Column("install_date", sa.Date(), nullable=True),
        sa.Column("ditto_thing_id", sa.String(), nullable=False),
        sa.Column("aas_id", sa.String(), nullable=True),
        sa.Column("fidelity_level", sa.SmallInteger(), server_default="2", nullable=False),
        sa.Column("ideal_cycle_time_s", sa.Numeric(10, 3), nullable=True),
        sa.Column("rated_power_kw", sa.Numeric(10, 3), nullable=True),
        sa.Column("model_3d_path", sa.String(), nullable=True),
        sa.Column("position", pg.JSONB(), nullable=True),
        sa.Column("status", sa.String(), server_default="RUNNING", nullable=False),
        sa.Column("attributes", pg.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "asset_type in ('cnc_mill', 'compressor', 'conveyor', 'hydraulic_press', 'injection_moulder', 'other')",
            name="ck_assets_asset_type",
        ),
        sa.CheckConstraint("status in ('RUNNING', 'IDLE', 'DOWN', 'MAINTENANCE', 'UNKNOWN')", name="ck_assets_status"),
        sa.CheckConstraint("fidelity_level between 1 and 4", name="ck_assets_fidelity_level"),
        sa.ForeignKeyConstraint(["line_id"], ["lines.id"], name="fk_assets_line_id_lines"),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
    )
    op.create_index("assets_code_uq", "assets", ["code"], unique=True, postgresql_where=ACTIVE)
    op.create_index("ix_assets_line_id", "assets", ["line_id"])

    op.create_table(
        "components",
        _pk(),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("component_type", sa.String(), nullable=False),
        sa.Column("health_weight", sa.Numeric(4, 3), server_default="1.0", nullable=False),
        sa.Column("physics_model", sa.String(), nullable=True),
        sa.Column("physics_params", pg.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_components_asset_id_assets"),
        sa.PrimaryKeyConstraint("id", name="pk_components"),
    )
    op.create_index("components_code_uq", "components", ["asset_id", "code"], unique=True, postgresql_where=ACTIVE)

    op.create_table(
        "sensors",
        _pk(),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("component_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("metric_name", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("sample_rate_hz", sa.Numeric(10, 3), server_default="1", nullable=False),
        sa.Column("min_valid", sa.Numeric(), nullable=True),
        sa.Column("max_valid", sa.Numeric(), nullable=True),
        sa.Column("warn_low", sa.Numeric(), nullable=True),
        sa.Column("warn_high", sa.Numeric(), nullable=True),
        sa.Column("alarm_low", sa.Numeric(), nullable=True),
        sa.Column("alarm_high", sa.Numeric(), nullable=True),
        sa.Column("adaptive_sigma", sa.Numeric(4, 2), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "kind in ('vibration', 'temperature', 'current', 'voltage', 'power', 'pressure', 'flow', "
            "'speed', 'torque', 'position', 'count', 'other')",
            name="ck_sensors_kind",
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_sensors_asset_id_assets"),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], name="fk_sensors_component_id_components"),
        sa.PrimaryKeyConstraint("id", name="pk_sensors"),
    )
    op.create_index("sensors_metric_uq", "sensors", ["asset_id", "metric_name"], unique=True, postgresql_where=ACTIVE)
    op.create_index("ix_sensors_component_id", "sensors", ["component_id"])

    op.create_table(
        "aas_submodels",
        _pk(),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("semantic_id", sa.String(), nullable=False),
        sa.Column("id_short", sa.String(), nullable=False),
        sa.Column("version", sa.String(), server_default="1.0", nullable=False),
        sa.Column("content", pg.JSONB(), nullable=False),
        *_timestamps(soft_delete=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_aas_submodels_asset_id_assets"),
        sa.PrimaryKeyConstraint("id", name="pk_aas_submodels"),
    )
    op.create_index("aas_submodels_uq", "aas_submodels", ["asset_id", "id_short"], unique=True)

    op.create_table(
        "failure_modes",
        _pk(),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("component_type", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("signature", pg.JSONB(), nullable=False),
        sa.Column("severity", sa.SmallInteger(), server_default="3", nullable=False),
        *_timestamps(soft_delete=False),
        sa.CheckConstraint("severity between 1 and 4", name="ck_failure_modes_severity"),
        sa.PrimaryKeyConstraint("id", name="pk_failure_modes"),
    )
    op.create_index("failure_modes_uq", "failure_modes", ["asset_type", "code"], unique=True)


def downgrade() -> None:
    op.drop_table("failure_modes")
    op.drop_table("aas_submodels")
    op.drop_table("sensors")
    op.drop_table("components")
    op.drop_table("assets")
    op.drop_table("lines")
    op.drop_table("plants")
