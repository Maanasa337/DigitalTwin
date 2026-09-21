"""REST endpoints for reporting (M10)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.pagination import PageParams, page_params
from app.common.schemas import Page
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import WRITE_ROLES, CurrentUser, get_current_user, require_role
from app.modules.reports.schemas import (
    ReportCreate,
    ReportDetail,
    ReportOut,
    ReportStatus,
    ReportType,
    ScheduleCreate,
    ScheduleOut,
    ScheduleUpdate,
)
from app.modules.reports.service import ReportScheduleService, ReportService

router = APIRouter(tags=["reports"])
reader = Depends(get_current_user)
writer = Depends(require_role(*WRITE_ROLES))


@router.post("/reports", response_model=ReportOut, status_code=status.HTTP_202_ACCEPTED)
def create_report(
    data: ReportCreate,
    user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Queue a report. 202: the file is produced by the worker, not in this request."""
    return ReportService(session, settings=settings).request(user, data)


@router.get("/reports", response_model=Page[ReportOut])
def list_reports(
    type: ReportType | None = None,
    status: ReportStatus | None = None,
    params: PageParams = Depends(page_params),
    user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Any:
    items, total = ReportService(session, settings=settings).list_reports(user, params, type_=type, status=status)
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.get("/reports/{report_id}", response_model=ReportDetail, dependencies=[reader])
def get_report(
    report_id: uuid.UUID,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Any:
    return ReportService(session, settings=settings).get_or_404(report_id)


@router.get("/reports/{report_id}/file")
def get_report_file(
    report_id: uuid.UUID,
    download: bool = Query(False, description="Force a download instead of inline preview"),
    user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    content, media_type, filename = ReportService(session, settings=settings).file(user, report_id)
    disposition = "attachment" if download else "inline"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


# ── Schedules (FR-RP-03) ──────────────────────────────────────────────


@router.get("/report-schedules", response_model=Page[ScheduleOut], dependencies=[reader])
def list_schedules(params: PageParams = Depends(page_params), session: Session = Depends(get_session)) -> Any:
    items, total = ReportScheduleService(session).list_schedules(params)
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.post("/report-schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(
    data: ScheduleCreate,
    user: CurrentUser = writer,
    session: Session = Depends(get_session),
) -> Any:
    return ReportScheduleService(session).create_schedule(user, data)


@router.patch("/report-schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: uuid.UUID,
    data: ScheduleUpdate,
    user: CurrentUser = writer,
    session: Session = Depends(get_session),
) -> Any:
    return ReportScheduleService(session).update_schedule(user, schedule_id, data)


@router.delete("/report-schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    schedule_id: uuid.UUID,
    user: CurrentUser = writer,
    session: Session = Depends(get_session),
) -> None:
    ReportScheduleService(session).delete_schedule(user, schedule_id)
