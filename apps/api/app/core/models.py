import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, PKMixin, TimestampMixin


class User(PKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    keycloak_sub: Mapped[str] = mapped_column(unique=True)
    display_name: Mapped[str]
    email: Mapped[str | None]
    roles: Mapped[list[str]] = mapped_column(server_default=text("'{}'"))
    locale: Mapped[str] = mapped_column(server_default="en")
    last_seen_at: Mapped[datetime | None]


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("actor_kind in ('user','system','voice','edge')", name="actor_kind"),
        Index("ix_audit_log_entity_entity_id_at", "entity", "entity_id", text("at desc")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(server_default=func.now())
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_kind: Mapped[str]
    entity: Mapped[str]
    entity_id: Mapped[uuid.UUID | None]
    action: Mapped[str]
    before: Mapped[dict[str, Any] | None]
    after: Mapped[dict[str, Any] | None]
    request_id: Mapped[str | None]
    ip: Mapped[str | None]
