import uuid
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, inspect
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import Base
from app.core.models import AuditLog, User
from app.core.observability import client_ip_var, request_id_var
from app.core.security import CurrentUser


def ensure_user(session: Session, user: CurrentUser) -> uuid.UUID:
    stmt = (
        insert(User)
        .values(
            keycloak_sub=user.sub,
            display_name=user.name,
            email=user.email,
            roles=sorted(user.roles),
            last_seen_at=func.now(),
        )
        .on_conflict_do_update(
            index_elements=[User.keycloak_sub],
            set_={
                "display_name": user.name,
                "email": user.email,
                "roles": sorted(user.roles),
                "last_seen_at": func.now(),
                "updated_at": func.now(),
            },
        )
        .returning(User.id)
    )
    return session.execute(stmt).scalar_one()


def snapshot(obj: Base) -> dict[str, Any]:
    return jsonable_encoder({attr.key: getattr(obj, attr.key) for attr in inspect(obj).mapper.column_attrs})


def write_audit(
    session: Session,
    *,
    actor: CurrentUser | None,
    entity: str,
    entity_id: uuid.UUID | None,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Adds the audit row to the caller's transaction; the caller commits both together."""
    session.add(
        AuditLog(
            actor_id=ensure_user(session, actor) if actor else None,
            actor_kind="user" if actor else "system",
            entity=entity,
            entity_id=entity_id,
            action=action,
            before=jsonable_encoder(before) if before is not None else None,
            after=jsonable_encoder(after) if after is not None else None,
            request_id=request_id_var.get(),
            ip=client_ip_var.get(),
        )
    )
    session.flush()
