"""core: users, audit_log

Revision ID: 0001_core
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSTZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("keycloak_sub", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("roles", pg.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("locale", sa.String(), server_default="en", nullable=False),
        sa.Column("last_seen_at", TSTZ, nullable=True),
        sa.Column("created_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("keycloak_sub", name="uq_users_keycloak_sub"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("at", TSTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_kind", sa.String(), nullable=False),
        sa.Column("entity", sa.String(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("before", pg.JSONB(), nullable=True),
        sa.Column("after", pg.JSONB(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.CheckConstraint("actor_kind in ('user','system','voice','edge')", name="ck_audit_log_actor_kind"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_audit_log_actor_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_log_entity_entity_id_at", "audit_log", ["entity", "entity_id", sa.text("at desc")])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("users")
