"""xai: knowledge base, explanations, counterfactuals, narrations, audits, feedback, quality metrics

Revision ID: 0006_xai
Revises: 0005_pdm
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0006_xai"
down_revision: str | None = "0005_pdm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSTZ = sa.DateTime(timezone=True)


def _pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    # ── knowledge_base_entries ────────────────────────────────────────
    # Specified in ARCHITECTURE §7.2 but not created by 0002; M6 reason cards are its only reader.
    op.create_table(
        "knowledge_base_entries",
        _pk(),
        sa.Column("failure_mode_id", sa.Uuid(), nullable=False),
        sa.Column("symptom", sa.Text(), nullable=False),
        sa.Column("likely_cause", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("parts", pg.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("est_duration_min", sa.Integer(), nullable=True),
        sa.Column("lang", sa.String(), server_default="en", nullable=False),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["failure_mode_id"], ["failure_modes.id"], name="fk_knowledge_base_entries_failure_mode_id_failure_modes"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_base_entries"),
    )
    op.create_index(
        "knowledge_base_entries_mode_lang_uq", "knowledge_base_entries", ["failure_mode_id", "lang"], unique=True
    )

    # ── explanations ──────────────────────────────────────────────────
    # prediction_id carries no FK: `predictions` is a hypertable and Timescale forbids inbound FKs to it.
    op.create_table(
        "explanations",
        _pk(),
        sa.Column("prediction_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("base_value", sa.Float(), nullable=True),
        sa.Column("attributions", pg.JSONB(), nullable=False),
        sa.Column("temporal_attribution", pg.JSONB(), nullable=True),
        sa.Column("ebm_terms", pg.JSONB(), nullable=True),
        sa.Column("agreement", pg.JSONB(), nullable=True),
        sa.Column("reason_card", pg.JSONB(), nullable=True),
        sa.Column("compute_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "method in ('tree_shap','deep_shap','integrated_gradients','kernel_shap','ebm')",
            name="ck_explanations_method",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_explanations"),
    )
    # One explanation per prediction: the explain task is retried, and a retry must not duplicate.
    op.create_index("explanations_prediction_id_uq", "explanations", ["prediction_id"], unique=True)

    # ── counterfactuals ───────────────────────────────────────────────
    op.create_table(
        "counterfactuals",
        _pk(),
        sa.Column("explanation_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("target", sa.String(), nullable=False),
        sa.Column("changes", pg.JSONB(), nullable=False),
        sa.Column("outcome", pg.JSONB(), nullable=False),
        sa.Column("feasibility_score", sa.Float(), nullable=True),
        sa.Column("action_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["explanation_id"], ["explanations.id"], name="fk_counterfactuals_explanation_id_explanations"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_counterfactuals"),
    )
    op.create_index("ix_counterfactuals_explanation_id", "counterfactuals", ["explanation_id"])

    # ── narrations ────────────────────────────────────────────────────
    op.create_table(
        "narrations",
        _pk(),
        sa.Column("explanation_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("lang", sa.String(), server_default="en", nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("llm_text", sa.Text(), nullable=True),
        sa.Column("llm_model", sa.String(), nullable=True),
        sa.Column("llm_prompt_hash", sa.String(), nullable=True),
        sa.Column("final_text", sa.Text(), nullable=False),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "kind in ('status','why','confidence','counterfactual','report_summary')", name="ck_narrations_kind"
        ),
        sa.ForeignKeyConstraint(
            ["explanation_id"], ["explanations.id"], name="fk_narrations_explanation_id_explanations"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_narrations"),
    )
    op.create_index(
        "narrations_explanation_kind_lang_uq", "narrations", ["explanation_id", "kind", "lang"], unique=True
    )

    # ── narration_audits ──────────────────────────────────────────────
    op.create_table(
        "narration_audits",
        _pk(),
        sa.Column("narration_id", sa.Uuid(), nullable=False),
        sa.Column("rank_agreement", sa.Float(), nullable=False),
        sa.Column("sign_agreement", sa.Float(), nullable=False),
        sa.Column("numeric_within_tolerance", sa.Boolean(), nullable=False),
        sa.Column("hallucinated_features", pg.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("unsupported_recommendation", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("details", pg.JSONB(), nullable=True),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["narration_id"], ["narrations.id"], name="fk_narration_audits_narration_id_narrations"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_narration_audits"),
    )
    op.create_index("ix_narration_audits_narration_id", "narration_audits", ["narration_id"])
    op.create_index("ix_narration_audits_created_at", "narration_audits", [sa.text("created_at DESC")])

    # ── explanation_feedback ──────────────────────────────────────────
    op.create_table(
        "explanation_feedback",
        _pk(),
        sa.Column("explanation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("suspect_sensor_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("verdict in ('agree','disagree','unsure')", name="ck_explanation_feedback_verdict"),
        sa.CheckConstraint("channel in ('ui','voice','chat')", name="ck_explanation_feedback_channel"),
        sa.ForeignKeyConstraint(
            ["explanation_id"], ["explanations.id"], name="fk_explanation_feedback_explanation_id_explanations"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_explanation_feedback_user_id_users"),
        sa.ForeignKeyConstraint(
            ["suspect_sensor_id"], ["sensors.id"], name="fk_explanation_feedback_suspect_sensor_id_sensors"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_explanation_feedback"),
    )
    op.create_index("ix_explanation_feedback_explanation_id", "explanation_feedback", ["explanation_id"])

    # ── explanation_quality_metrics ───────────────────────────────────
    op.create_table(
        "explanation_quality_metrics",
        _pk(),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("dataset_ref", sa.String(), nullable=True),
        sa.Column("computed_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], name="fk_explanation_quality_metrics_model_id_models"),
        sa.PrimaryKeyConstraint("id", name="pk_explanation_quality_metrics"),
    )
    op.create_index(
        "ix_explanation_quality_metrics_model_id_metric", "explanation_quality_metrics", ["model_id", "metric"]
    )

    # ── sensor quality flag (FR-XAI-09) ───────────────────────────────
    # A "disagree" verdict naming a sensor suppresses confidence for that sensor until the flag expires.
    op.add_column("sensors", sa.Column("quality_flag", sa.String(), nullable=True))
    op.add_column("sensors", sa.Column("quality_flag_until", TSTZ, nullable=True))


def downgrade() -> None:
    op.drop_column("sensors", "quality_flag_until")
    op.drop_column("sensors", "quality_flag")
    op.drop_table("explanation_quality_metrics")
    op.drop_table("explanation_feedback")
    op.drop_table("narration_audits")
    op.drop_table("narrations")
    op.drop_table("counterfactuals")
    op.drop_table("explanations")
    op.drop_table("knowledge_base_entries")
