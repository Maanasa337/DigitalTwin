"""REST endpoints for telemetry, alarms, and alarm rules (M3)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.common.schemas import Page
from app.core.db import get_session
from app.core.security import CurrentUser, get_current_user, require_role
from app.modules.telemetry.schemas import (
    AggLevel,
    AlarmActionCreate,
    AlarmOut,
    AlarmRuleCreate,
    AlarmRuleOut,
    AlarmRuleUpdate,
    TelemetryLatestResponse,
    TelemetrySeries,
)
from app.modules.telemetry.service import AlarmRuleService, AlarmService, TelemetryService

router = APIRouter(tags=["telemetry"])


# ── Telemetry ─────────────────────────────────────────────────────────


@router.get("/telemetry", response_model=list[TelemetrySeries])
def query_telemetry(
    asset: uuid.UUID,
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    sensors: str | None = Query(None, description="Comma-separated sensor codes"),
    agg: AggLevel | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[TelemetrySeries]:
    sensor_list = [s.strip() for s in sensors.split(",")] if sensors else None
    return TelemetryService(session).query(asset, sensor_list, start, end, agg)


@router.get("/telemetry/latest", response_model=TelemetryLatestResponse)
def telemetry_latest(
    asset: uuid.UUID,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> TelemetryLatestResponse:
    return TelemetryService(session).latest(asset)


# ── Alarms ────────────────────────────────────────────────────────────


@router.get("/alarms", response_model=Page[AlarmOut])
def list_alarms(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    severity: str | None = None,
    status: str | None = None,
    asset_id: uuid.UUID | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    items, total = AlarmService(session).list_alarms(PageParams(page=page, size=size), severity, status, asset_id)
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("/alarms/{alarm_id}/ack", response_model=AlarmOut)
def ack_alarm(
    alarm_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> AlarmOut:
    alarm = AlarmService(session).perform_action(user, alarm_id, AlarmActionCreate(action="ack"))
    return AlarmOut.model_validate(alarm)


@router.post("/alarms/{alarm_id}/assign", response_model=AlarmOut)
def assign_alarm(
    alarm_id: uuid.UUID,
    body: AlarmActionCreate,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> AlarmOut:
    body.action = "assign"  # type: ignore[assignment]
    alarm = AlarmService(session).perform_action(user, alarm_id, body)
    return AlarmOut.model_validate(alarm)


@router.post("/alarms/{alarm_id}/comment", response_model=AlarmOut)
def comment_alarm(
    alarm_id: uuid.UUID,
    body: AlarmActionCreate,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> AlarmOut:
    body.action = "comment"  # type: ignore[assignment]
    alarm = AlarmService(session).perform_action(user, alarm_id, body)
    return AlarmOut.model_validate(alarm)


@router.post("/alarms/{alarm_id}/shelve", response_model=AlarmOut)
def shelve_alarm(
    alarm_id: uuid.UUID,
    body: AlarmActionCreate,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> AlarmOut:
    body.action = "shelve"  # type: ignore[assignment]
    alarm = AlarmService(session).perform_action(user, alarm_id, body)
    return AlarmOut.model_validate(alarm)


@router.post("/alarms/bulk-ack")
def bulk_ack_alarms(
    alarm_ids: list[uuid.UUID],
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    count = AlarmService(session).bulk_ack(user, alarm_ids)
    return {"acknowledged": count}


# ── Alarm Rules ───────────────────────────────────────────────────────


@router.get("/alarm-rules", response_model=Page[AlarmRuleOut])
def list_alarm_rules(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    items, total = AlarmRuleService(session).list_rules(PageParams(page=page, size=size))
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("/alarm-rules", response_model=AlarmRuleOut, status_code=201)
def create_alarm_rule(
    body: AlarmRuleCreate,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(require_role("engineer", "admin")),
) -> AlarmRuleOut:
    rule = AlarmRuleService(session).create_rule(user, body)
    return AlarmRuleOut.model_validate(rule)


@router.patch("/alarm-rules/{rule_id}", response_model=AlarmRuleOut)
def update_alarm_rule(
    rule_id: uuid.UUID,
    body: AlarmRuleUpdate,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(require_role("engineer", "admin")),
) -> AlarmRuleOut:
    rule = AlarmRuleService(session).update_rule(user, rule_id, body)
    return AlarmRuleOut.model_validate(rule)
