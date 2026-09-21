import time
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

import valkey
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.common.pagination import PageParams, page_params
from app.common.schemas import ORMModel, Page
from app.core.audit import ensure_user
from app.core.config import get_settings
from app.core.db import get_session
from app.core.models import AuditLog, User
from app.core.security import WRITE_ROLES, CurrentUser, get_current_user, get_token_verifier, require_role

router = APIRouter(tags=["core"])


class MeOut(ORMModel):
    id: uuid.UUID
    sub: str
    display_name: str
    email: str | None
    roles: list[str]
    locale: str


class AuditOut(ORMModel):
    id: int
    at: datetime
    actor_id: uuid.UUID | None
    actor_name: str | None = None
    actor_kind: str
    entity: str
    entity_id: uuid.UUID | None
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    request_id: str | None
    ip: str | None


class DependencyStatus(BaseModel):
    ok: bool
    latency_ms: float
    error: str | None = None


class HealthOut(BaseModel):
    status: str
    dependencies: dict[str, DependencyStatus]


def _probe(check: Callable[[], Any]) -> DependencyStatus:
    started = time.perf_counter()
    try:
        check()
        return DependencyStatus(ok=True, latency_ms=round((time.perf_counter() - started) * 1000, 1))
    except Exception as exc:
        return DependencyStatus(
            ok=False, latency_ms=round((time.perf_counter() - started) * 1000, 1), error=str(exc)[:200]
        )


@router.get("/health", response_model=HealthOut)
def health(request: Request, session: Session = Depends(get_session)) -> HealthOut:
    settings = get_settings()
    state = request.app.state

    def valkey_ping() -> None:
        with valkey.Valkey.from_url(settings.valkey_url, socket_timeout=2, socket_connect_timeout=2) as client:
            client.ping()

    def mqtt() -> None:
        if not state.commands.connected:
            raise RuntimeError("not connected")

    checks = {
        "database": _probe(lambda: session.execute(text("select 1"))),
        "valkey": _probe(valkey_ping),
        "mqtt": _probe(mqtt),
        "ditto": _probe(state.ditto.ping),
        "keycloak": _probe(get_token_verifier().ping),
        "simulator": _probe(lambda: state.simulator.request("GET", "/health", timeout=2)),
    }
    return HealthOut(status="ok" if all(c.ok for c in checks.values()) else "degraded", dependencies=checks)


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser = Depends(get_current_user), session: Session = Depends(get_session)) -> Any:
    user_id = ensure_user(session, user)
    session.commit()
    row = session.get(User, user_id)
    assert row is not None
    return MeOut(
        id=row.id,
        sub=row.keycloak_sub,
        display_name=row.display_name,
        email=row.email,
        roles=row.roles,
        locale=row.locale,
    )


@router.get("/audit", response_model=Page[AuditOut], dependencies=[Depends(require_role(*WRITE_ROLES))])
def audit(
    entity: str | None = Query(None, max_length=64),
    entity_id: uuid.UUID | None = Query(None, alias="id"),
    params: PageParams = Depends(page_params),
    session: Session = Depends(get_session),
) -> Any:
    filters = []
    if entity:
        filters.append(AuditLog.entity == entity)
    if entity_id:
        filters.append(AuditLog.entity_id == entity_id)
    total = session.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0
    rows = session.execute(
        select(AuditLog, User.display_name)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(*filters)
        .order_by(AuditLog.at.desc(), AuditLog.id.desc())
        .offset((params.page - 1) * params.size)
        .limit(params.size)
    ).all()
    items = [AuditOut.model_validate(log).model_copy(update={"actor_name": name}) for log, name in rows]
    return Page(items=items, total=total, page=params.page, size=params.size)
