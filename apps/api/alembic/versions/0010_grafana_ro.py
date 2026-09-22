"""grafana: read-only login role for the provisioned Grafana datasource

Revision ID: 0010_grafana_ro
Revises: 0009_voice_reports

Roles are cluster-wide, so the role is created only when missing (the test database shares the
cluster with the dev one) and its password is (re)set on every upgrade. Grants are per database.
Nothing here touches ORM metadata, so `alembic check` stays clean.

Continuous aggregates (`telemetry_1m`, `telemetry_1h`) are views; a view runs with its owner's
privileges on the materialised hypertable and the raw `telemetry` it unions for real-time rows,
so SELECT on the view is enough. TimescaleDB also propagates GRANTs on a hypertable to its chunks.
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0010_grafana_ro"
down_revision: str | None = "0009_voice_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE = "grafana_ro"

TABLES = (
    "telemetry",
    "telemetry_1m",
    "telemetry_1h",
    "sensors",
    "assets",
    "lines",
    "plants",
    "components",
    "predictions",
    "energy_readings",
    "production_counts",
    "asset_state_events",
    "alarms",
    "kpi_values",
    "kpi_definitions",
    "models",
)


def _password() -> str:
    # Must match GRAFANA_DB_PASSWORD, which compose hands to both the api (as TV_GRAFANA_DB_PASSWORD)
    # and the Grafana datasource.
    return os.environ.get("TV_GRAFANA_DB_PASSWORD") or "grafana_ro"


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    password = _literal(_password())
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} LOGIN PASSWORD {password};
            ELSE
                ALTER ROLE {ROLE} WITH LOGIN PASSWORD {password};
            END IF;
        END
        $$;
        """
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format('GRANT CONNECT ON DATABASE %I TO {ROLE}', current_database());
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    op.execute(f"GRANT SELECT ON {', '.join(TABLES)} TO {ROLE}")


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                EXECUTE 'REVOKE SELECT ON {", ".join(TABLES)} FROM {ROLE}';
                EXECUTE 'REVOKE USAGE ON SCHEMA public FROM {ROLE}';
                EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM {ROLE}', current_database());
                -- The role is cluster-wide: another database (dev vs test) may still grant it
                -- privileges, and then DROP ROLE would fail. Keep it in that case.
                IF NOT EXISTS (
                    SELECT 1 FROM pg_shdepend d JOIN pg_roles r ON r.oid = d.refobjid
                    WHERE r.rolname = '{ROLE}'
                ) THEN
                    DROP ROLE {ROLE};
                END IF;
            END IF;
        END
        $$;
        """
    )
