"""voice: sessions, turns, actions, intent examples; reports: reports and schedules

Revision ID: 0009_voice_reports
Revises: 0008_analytics
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0009_voice_reports"
down_revision: str | None = "0008_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSTZ = sa.DateTime(timezone=True)
ACTIVE = sa.text("deleted_at IS NULL")


def _pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    # ── voice_sessions ────────────────────────────────────────────────
    op.create_table(
        "voice_sessions",
        _pk(),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", TSTZ, nullable=True),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("device", sa.String(), nullable=True),
        sa.Column("lang", sa.String(), server_default="en", nullable=False),
        sa.Column("context", pg.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.CheckConstraint("channel in ('voice','chat')", name="ck_voice_sessions_channel"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_voice_sessions_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_voice_sessions"),
    )
    op.create_index("ix_voice_sessions_user_id_started_at", "voice_sessions", ["user_id", sa.text("started_at DESC")])

    # ── voice_turns ───────────────────────────────────────────────────
    op.create_table(
        "voice_turns",
        _pk(),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("transcript_confidence", sa.Float(), nullable=True),
        sa.Column("stt_ms", sa.Integer(), nullable=True),
        sa.Column("intent", sa.String(), nullable=True),
        sa.Column("slots", pg.JSONB(), nullable=True),
        sa.Column("intent_confidence", sa.Float(), nullable=True),
        sa.Column("router", sa.String(), nullable=True),
        sa.Column("router_ms", sa.Integer(), nullable=True),
        sa.Column("tier", sa.String(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("citations", pg.JSONB(), nullable=True),
        sa.Column("tts_ms", sa.Integer(), nullable=True),
        sa.Column("total_ms", sa.Integer(), nullable=True),
        sa.Column("snr_db", sa.Float(), nullable=True),
        sa.Column("audio_uri", sa.String(), nullable=True),
        sa.CheckConstraint("router is null or router in ('rules','llm','none')", name="ck_voice_turns_router"),
        sa.CheckConstraint("tier is null or tier in ('T0','T1','T2','T3')", name="ck_voice_turns_tier"),
        sa.ForeignKeyConstraint(["session_id"], ["voice_sessions.id"], name="fk_voice_turns_session_id_voice_sessions"),
        sa.PrimaryKeyConstraint("id", name="pk_voice_turns"),
    )
    op.create_index("ix_voice_turns_session_id_at", "voice_turns", ["session_id", "at"])

    # ── voice_actions ─────────────────────────────────────────────────
    op.create_table(
        "voice_actions",
        _pk(),
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("params", pg.JSONB(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("readback", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("validation_errors", pg.JSONB(), nullable=True),
        sa.Column("expires_at", TSTZ, nullable=True),
        sa.Column("confirmed_at", TSTZ, nullable=True),
        sa.Column("second_factor_ok", sa.Boolean(), nullable=True),
        sa.Column("executed_at", TSTZ, nullable=True),
        sa.Column("result", pg.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("tier in ('T0','T1','T2','T3')", name="ck_voice_actions_tier"),
        sa.CheckConstraint(
            "status in ('pending','confirmed','cancelled','expired','executed','failed','rejected')",
            name="ck_voice_actions_status",
        ),
        sa.ForeignKeyConstraint(["turn_id"], ["voice_turns.id"], name="fk_voice_actions_turn_id_voice_turns"),
        sa.PrimaryKeyConstraint("id", name="pk_voice_actions"),
    )
    op.create_index("ix_voice_actions_status", "voice_actions", ["status"])
    op.create_index("ix_voice_actions_turn_id", "voice_actions", ["turn_id"])

    # ── intent_examples ───────────────────────────────────────────────
    op.create_table(
        "intent_examples",
        _pk(),
        sa.Column("intent", sa.String(), nullable=False),
        sa.Column("lang", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("slots", pg.JSONB(), nullable=True),
        sa.Column("noise_variant", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("split", sa.String(), server_default="test", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_intent_examples"),
    )
    # The suite is regenerated from intents.yaml; the same utterance must not accumulate rows.
    op.create_index("intent_examples_uq", "intent_examples", ["intent", "lang", "text", "split"], unique=True)

    # ── report_schedules ──────────────────────────────────────────────
    op.create_table(
        "report_schedules",
        _pk(),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("format", sa.String(), nullable=False),
        sa.Column("cron", sa.String(), nullable=False),
        sa.Column("recipients", pg.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_run_at", TSTZ, nullable=True),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", TSTZ, nullable=True),
        sa.CheckConstraint(
            "type in ('machine_health','weekly_maintenance','energy','benchmark','incident')",
            name="ck_report_schedules_type",
        ),
        sa.CheckConstraint("format in ('pdf','docx','md','html')", name="ck_report_schedules_format"),
        sa.PrimaryKeyConstraint("id", name="pk_report_schedules"),
    )
    op.create_index("ix_report_schedules_enabled", "report_schedules", ["enabled"], postgresql_where=ACTIVE)

    # ── reports ───────────────────────────────────────────────────────
    op.create_table(
        "reports",
        _pk(),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("period_start", TSTZ, nullable=True),
        sa.Column("period_end", TSTZ, nullable=True),
        sa.Column("format", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="queued", nullable=False),
        sa.Column("file_uri", sa.String(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("summary_audit", pg.JSONB(), nullable=True),
        sa.Column("data", pg.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("requested_via", sa.String(), server_default="ui", nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", TSTZ, nullable=True),
        sa.CheckConstraint(
            "type in ('machine_health','weekly_maintenance','energy','benchmark','incident')",
            name="ck_reports_type",
        ),
        # `html` is the renderer's fallback when WeasyPrint's native libraries are absent, so it is a
        # real stored format rather than an error state.
        sa.CheckConstraint("format in ('pdf','docx','md','html')", name="ck_reports_format"),
        sa.CheckConstraint("status in ('queued','running','done','failed')", name="ck_reports_status"),
        sa.CheckConstraint("period_end is null or period_end > period_start", name="ck_reports_period"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], name="fk_reports_requested_by_users"),
        sa.ForeignKeyConstraint(
            ["schedule_id"], ["report_schedules.id"], name="fk_reports_schedule_id_report_schedules"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reports"),
    )
    op.create_index("ix_reports_type_created_at", "reports", ["type", sa.text("created_at DESC")])
    op.create_index("ix_reports_status", "reports", ["status"])


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("report_schedules")
    op.drop_table("intent_examples")
    op.drop_table("voice_actions")
    op.drop_table("voice_turns")
    op.drop_table("voice_sessions")
