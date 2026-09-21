"""pdm: models, model_metrics, predictions, benchmark_runs

Revision ID: 0005_pdm
Revises: 0004_telemetry
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0005_pdm"
down_revision: str | None = "0004_telemetry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSTZ = sa.DateTime(timezone=True)


def _pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    # ── models ────────────────────────────────────────────────────────
    op.create_table(
        "models",
        _pk(),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("task", sa.String(), nullable=False),
        sa.Column("algorithm", sa.String(), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=True),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("dataset_ref", sa.String(), nullable=False),
        sa.Column("dataset_hash", sa.String(), nullable=False),
        sa.Column("feature_set", pg.JSONB(), nullable=False),
        sa.Column("hyperparams", pg.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("window_size", sa.Integer(), nullable=True),
        sa.Column("stride", sa.Integer(), nullable=True),
        sa.Column("horizon", sa.Integer(), nullable=True),
        sa.Column("artifact_uri", sa.String(), nullable=False),
        sa.Column("onnx_uri", sa.String(), nullable=True),
        sa.Column("explainer_uri", sa.String(), nullable=True),
        sa.Column("calibrator_uri", sa.String(), nullable=True),
        sa.Column("conformal_uri", sa.String(), nullable=True),
        sa.Column("stage", sa.String(), server_default="candidate", nullable=False),
        sa.Column("trained_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("trained_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("task in ('anomaly','failure','rul','survival')", name="ck_models_task"),
        sa.CheckConstraint("stage in ('candidate','production','archived')", name="ck_models_stage"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_models_asset_id_assets"),
        sa.ForeignKeyConstraint(["trained_by"], ["users.id"], name="fk_models_trained_by_users"),
        sa.PrimaryKeyConstraint("id", name="pk_models"),
    )
    op.create_index("models_name_version_uq", "models", ["name", "version"], unique=True)
    op.create_index(
        "models_one_production_uq",
        "models",
        ["name", sa.text("coalesce(asset_id,'00000000-0000-0000-0000-000000000000'::uuid)")],
        unique=True,
        postgresql_where=sa.text("stage='production'"),
    )

    # ── model_metrics ─────────────────────────────────────────────────
    op.create_table(
        "model_metrics",
        _pk(),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("split", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("extra", pg.JSONB(), nullable=True),
        sa.CheckConstraint("split in ('train','val','test','calibration')", name="ck_model_metrics_split"),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], name="fk_model_metrics_model_id_models"),
        sa.PrimaryKeyConstraint("id", name="pk_model_metrics"),
    )
    op.create_index("ix_model_metrics_model_id", "model_metrics", ["model_id"])

    # ── predictions hypertable ────────────────────────────────────────
    op.create_table(
        "predictions",
        _pk(),
        sa.Column("time", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("component_id", sa.Uuid(), nullable=True),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("window_start", TSTZ, nullable=False),
        sa.Column("window_end", TSTZ, nullable=False),
        sa.Column("health_index", sa.Numeric(5, 2), nullable=True),
        sa.Column("anomaly_score", sa.Float(), nullable=True),
        sa.Column("failure_probability", pg.JSONB(), nullable=True),
        sa.Column("failure_probability_calibrated", pg.JSONB(), nullable=True),
        sa.Column("rul_point", sa.Float(), nullable=True),
        sa.Column("rul_low", sa.Float(), nullable=True),
        sa.Column("rul_high", sa.Float(), nullable=True),
        sa.Column("rul_unit", sa.String(), server_default="cycles", nullable=True),
        sa.Column("rul_coverage", sa.Numeric(3, 2), server_default="0.90", nullable=True),
        sa.Column("rul_physics_point", sa.Float(), nullable=True),
        sa.Column("rul_fused_point", sa.Float(), nullable=True),
        sa.Column("confidence_label", sa.String(), nullable=True),
        sa.Column("confidence_reasons", pg.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("drift_flag", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("drift_score", sa.Float(), nullable=True),
        sa.Column("ood_score", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), server_default="server", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "confidence_label in ('high','medium','low') OR confidence_label IS NULL",
            name="ck_predictions_confidence_label",
        ),
        sa.CheckConstraint("source in ('server','edge')", name="ck_predictions_source"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_predictions_asset_id_assets"),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], name="fk_predictions_component_id_components"),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], name="fk_predictions_model_id_models"),
    )
    # No primary key, like every other hypertable here: Timescale refuses a unique index that does
    # not contain the partitioning column, and `id` alone does not. The ORM still treats `id` as the
    # identity, and the uniqueness that matters is enforced by the (time, id) index below.
    op.execute("SELECT create_hypertable('predictions','time')")
    op.create_index("predictions_time_id_uq", "predictions", ["time", "id"], unique=True)
    op.create_index("ix_predictions_id", "predictions", ["id"])
    op.create_index("ix_predictions_asset_id_time", "predictions", ["asset_id", sa.text("time DESC")])

    # ── benchmark_runs ────────────────────────────────────────────────
    op.create_table(
        "benchmark_runs",
        _pk(),
        sa.Column("started_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", TSTZ, nullable=True),
        sa.Column("git_sha", sa.String(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("datasets", pg.ARRAY(sa.Text()), nullable=False),
        sa.Column("results", pg.JSONB(), nullable=True),
        sa.Column("report_uri", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default="running", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_benchmark_runs"),
    )


def downgrade() -> None:
    op.drop_table("benchmark_runs")
    op.execute("DROP TABLE predictions CASCADE")
    op.drop_table("model_metrics")
    op.drop_table("models")
