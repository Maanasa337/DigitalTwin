"""simulation: scenarios, scenario_runs

Revision ID: 0003_simulation
Revises: 0002_assets
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_simulation"
down_revision: str | None = "0002_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSTZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "scenarios",
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("yaml", sa.String(), nullable=False),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_scenarios"),
    )
    op.create_table(
        "scenario_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("scenario_code", sa.String(), nullable=True),
        sa.Column("started_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", TSTZ, nullable=True),
        sa.Column("time_scale", sa.Float(), server_default="1", nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("export_uri", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["scenario_code"], ["scenarios.code"], name="fk_scenario_runs_scenario_code_scenarios"),
        sa.PrimaryKeyConstraint("id", name="pk_scenario_runs"),
    )


def downgrade() -> None:
    op.drop_table("scenario_runs")
    op.drop_table("scenarios")
