"""telemetry: hypertables, aggregates, alarms, state events, energy, production

Revision ID: 0004_telemetry
Revises: 0003_simulation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0004_telemetry"
down_revision: str | None = "0003_simulation"
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
    # ── telemetry hypertable ──────────────────────────────────────────
    op.create_table(
        "telemetry",
        sa.Column("time", TSTZ, nullable=False),
        sa.Column("sensor_id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("quality", sa.SmallInteger(), server_default="192", nullable=False),
        sa.ForeignKeyConstraint(["sensor_id"], ["sensors.id"], name="fk_telemetry_sensor_id_sensors"),
    )
    op.execute("SELECT create_hypertable('telemetry','time', chunk_time_interval => interval '1 day')")
    op.create_index("ix_telemetry_sensor_id_time", "telemetry", ["sensor_id", sa.text("time DESC")])
    op.execute("ALTER TABLE telemetry SET (timescaledb.compress, timescaledb.compress_segmentby='sensor_id')")
    op.execute("SELECT add_compression_policy('telemetry', interval '7 days')")

    # ── continuous aggregate 1-minute ─────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW telemetry_1m
        WITH (timescaledb.continuous) AS
        SELECT time_bucket('1 minute', time) AS bucket,
               sensor_id,
               avg(value) AS avg, min(value) AS min, max(value) AS max,
               stddev(value) AS std, count(*) AS n
        FROM telemetry
        GROUP BY bucket, sensor_id
        WITH NO DATA
    """)
    op.execute("""
        SELECT add_continuous_aggregate_policy('telemetry_1m',
            start_offset  => interval '2 hours',
            end_offset    => interval '1 minute',
            schedule_interval => interval '1 minute')
    """)

    # ── continuous aggregate 1-hour ───────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW telemetry_1h
        WITH (timescaledb.continuous) AS
        SELECT time_bucket('1 hour', bucket) AS bucket,
               sensor_id,
               avg(avg) AS avg, min(min) AS min, max(max) AS max,
               avg(std) AS std, sum(n) AS n
        FROM telemetry_1m
        GROUP BY 1, sensor_id
        WITH NO DATA
    """)
    op.execute("""
        SELECT add_continuous_aggregate_policy('telemetry_1h',
            start_offset  => interval '25 hours',
            end_offset    => interval '1 hour',
            schedule_interval => interval '1 hour')
    """)

    # ── waveforms ─────────────────────────────────────────────────────
    op.create_table(
        "waveforms",
        sa.Column("time", TSTZ, nullable=False),
        sa.Column("sensor_id", sa.Uuid(), nullable=False),
        sa.Column("sample_rate_hz", sa.Integer(), nullable=False),
        sa.Column("n_samples", sa.Integer(), nullable=False),
        sa.Column("samples", sa.LargeBinary(), nullable=False),
        sa.Column("features", pg.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["sensor_id"], ["sensors.id"], name="fk_waveforms_sensor_id_sensors"),
    )
    op.execute("SELECT create_hypertable('waveforms','time')")

    # ── energy_readings ───────────────────────────────────────────────
    op.create_table(
        "energy_readings",
        sa.Column("time", TSTZ, nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("power_kw", sa.Float(), nullable=False),
        sa.Column("energy_kwh", sa.Float(), nullable=False),
        sa.Column("power_factor", sa.Float(), nullable=True),
        sa.Column("current_a", sa.Float(), nullable=True),
        sa.Column("voltage_v", sa.Float(), nullable=True),
        sa.Column("tariff_rate", sa.Numeric(10, 4), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_energy_readings_asset_id_assets"),
    )
    op.execute("SELECT create_hypertable('energy_readings','time')")
    op.create_index("ix_energy_readings_asset_id_time", "energy_readings", ["asset_id", sa.text("time DESC")])

    # ── production_counts ─────────────────────────────────────────────
    op.create_table(
        "production_counts",
        sa.Column("time", TSTZ, nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("shift_id", sa.Uuid(), nullable=True),
        sa.Column("good_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reject_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cycle_time_s", sa.Float(), nullable=True),
        sa.Column("planned", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_production_counts_asset_id_assets"),
    )
    op.execute("SELECT create_hypertable('production_counts','time')")

    # ── asset_state_events ────────────────────────────────────────────
    op.create_table(
        "asset_state_events",
        sa.Column("time", TSTZ, nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("cause_code", sa.String(), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), server_default="simulator", nullable=False),
        sa.CheckConstraint(
            "state in ('RUNNING','IDLE','DOWN','MAINTENANCE','UNKNOWN')", name="ck_asset_state_events_state"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_asset_state_events_asset_id_assets"),
    )
    op.execute("SELECT create_hypertable('asset_state_events','time')")

    # ── alarm_rules ───────────────────────────────────────────────────
    op.create_table(
        "alarm_rules",
        _pk(),
        sa.Column("sensor_id", sa.Uuid(), nullable=True),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("params", pg.JSONB(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "kind in ('threshold','adaptive','ml_anomaly','energy_intensity')", name="ck_alarm_rules_kind"
        ),
        sa.CheckConstraint("severity in ('info','warning','serious','critical')", name="ck_alarm_rules_severity"),
        sa.ForeignKeyConstraint(["sensor_id"], ["sensors.id"], name="fk_alarm_rules_sensor_id_sensors"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_alarm_rules_asset_id_assets"),
        sa.PrimaryKeyConstraint("id", name="pk_alarm_rules"),
    )

    # ── alarms ────────────────────────────────────────────────────────
    op.create_table(
        "alarms",
        _pk(),
        sa.Column("raised_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("cleared_at", TSTZ, nullable=True),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("sensor_id", sa.Uuid(), nullable=True),
        sa.Column("rule_id", sa.Uuid(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("prediction_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(), server_default="active", nullable=False),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        sa.Column("acknowledged_at", TSTZ, nullable=True),
        sa.Column("assigned_to", sa.Uuid(), nullable=True),
        sa.Column("shelved_until", TSTZ, nullable=True),
        sa.CheckConstraint("severity in ('info','warning','serious','critical')", name="ck_alarms_severity"),
        sa.CheckConstraint("status in ('active','acknowledged','shelved','cleared')", name="ck_alarms_status"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_alarms_asset_id_assets"),
        sa.ForeignKeyConstraint(["sensor_id"], ["sensors.id"], name="fk_alarms_sensor_id_sensors"),
        sa.ForeignKeyConstraint(["rule_id"], ["alarm_rules.id"], name="fk_alarms_rule_id_alarm_rules"),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], name="fk_alarms_acknowledged_by_users"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], name="fk_alarms_assigned_to_users"),
        sa.PrimaryKeyConstraint("id", name="pk_alarms"),
    )
    op.create_index("ix_alarms_asset_id_status_raised_at", "alarms", ["asset_id", "status", sa.text("raised_at DESC")])

    # ── alarm_actions ─────────────────────────────────────────────────
    op.create_table(
        "alarm_actions",
        _pk(),
        sa.Column("alarm_id", sa.Uuid(), nullable=False),
        sa.Column("at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.CheckConstraint(
            "action in ('ack','assign','comment','shelve','unshelve','clear')", name="ck_alarm_actions_action"
        ),
        sa.ForeignKeyConstraint(["alarm_id"], ["alarms.id"], name="fk_alarm_actions_alarm_id_alarms"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_alarm_actions_actor_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_alarm_actions"),
    )


def downgrade() -> None:
    op.drop_table("alarm_actions")
    op.drop_table("alarms")
    op.drop_table("alarm_rules")
    op.execute("DROP TABLE asset_state_events CASCADE")
    op.execute("DROP TABLE production_counts CASCADE")
    op.execute("DROP TABLE energy_readings CASCADE")
    op.execute("DROP TABLE waveforms CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS telemetry_1h CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS telemetry_1m CASCADE")
    op.execute("SELECT remove_compression_policy('telemetry', if_exists => true)")
    op.execute("DROP TABLE telemetry CASCADE")
