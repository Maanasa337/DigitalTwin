"""REST endpoints for maintenance scheduling (M7)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.pagination import PageParams, page_params
from app.common.schemas import Page
from app.core.db import get_session
from app.core.security import WRITE_ROLES, CurrentUser, get_current_user, require_role
from app.dependencies import get_command_sender
from app.modules.maintenance.schemas import (
    AvailabilityCreate,
    AvailabilityOut,
    ExportFormat,
    OptimiseRequest,
    ScheduleDetail,
    ScheduleItemOut,
    ScheduleItemPatch,
    TechnicianCreate,
    TechnicianOut,
    WorkOrderClose,
    WorkOrderCreate,
    WorkOrderDetail,
    WorkOrderOut,
    WorkOrderRiskOut,
    WorkOrderStatus,
    WorkOrderType,
    WorkOrderUpdate,
)
from app.modules.maintenance.service import ScheduleService, TechnicianService, WorkOrderService
from app.modules.twin.service import CommandSender

router = APIRouter(tags=["maintenance"])
reader = Depends(get_current_user)
writer = Depends(require_role(*WRITE_ROLES))
# Closing an order is the technician's own job, so it is not restricted to the write roles.
planner = Depends(require_role("technician", "manager", *WRITE_ROLES))


def work_order_service(
    session: Session = Depends(get_session), commands: CommandSender = Depends(get_command_sender)
) -> WorkOrderService:
    return WorkOrderService(session, commands)


# ── Technicians ───────────────────────────────────────────────────────


@router.get("/technicians", response_model=Page[TechnicianOut], dependencies=[reader])
def list_technicians(params: PageParams = Depends(page_params), session: Session = Depends(get_session)) -> Any:
    items, total = TechnicianService(session).repo.list(params)
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.post("/technicians", response_model=TechnicianOut, status_code=status.HTTP_201_CREATED)
def create_technician(
    data: TechnicianCreate, user: CurrentUser = writer, session: Session = Depends(get_session)
) -> Any:
    return TechnicianService(session).create_technician(user, data)


@router.get("/technicians/{technician_id}/availability", response_model=list[AvailabilityOut], dependencies=[reader])
def list_availability(
    technician_id: uuid.UUID,
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    session: Session = Depends(get_session),
) -> Any:
    return TechnicianService(session).availability(technician_id, start, end)


@router.post(
    "/technicians/{technician_id}/availability",
    response_model=AvailabilityOut,
    status_code=status.HTTP_201_CREATED,
)
def create_availability(
    technician_id: uuid.UUID,
    data: AvailabilityCreate,
    user: CurrentUser = writer,
    session: Session = Depends(get_session),
) -> Any:
    return TechnicianService(session).add_availability(user, technician_id, data)


# ── Work orders ───────────────────────────────────────────────────────


@router.get("/work-orders", response_model=Page[WorkOrderOut], dependencies=[reader])
def list_work_orders(
    asset_id: uuid.UUID | None = None,
    status_: WorkOrderStatus | None = Query(None, alias="status"),
    type_: WorkOrderType | None = Query(None, alias="type"),
    technician_id: uuid.UUID | None = None,
    open_only: bool = False,
    params: PageParams = Depends(page_params),
    session: Session = Depends(get_session),
) -> Any:
    items, total = WorkOrderService(session).list_orders(
        params, asset_id=asset_id, status=status_, type_=type_, technician_id=technician_id, open_only=open_only
    )
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.get("/work-orders/export", dependencies=[reader])
def export_work_orders(
    fmt: ExportFormat = Query("csv", alias="format"),
    asset_id: uuid.UUID | None = None,
    status_: WorkOrderStatus | None = Query(None, alias="status"),
    session: Session = Depends(get_session),
) -> Response:
    content, media_type, filename = WorkOrderService(session).export(fmt, asset_id=asset_id, status=status_)
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/work-orders", response_model=WorkOrderOut, status_code=status.HTTP_201_CREATED)
def create_work_order(
    data: WorkOrderCreate, user: CurrentUser = planner, session: Session = Depends(get_session)
) -> Any:
    return WorkOrderService(session).create_order(user, data)


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderDetail, dependencies=[reader])
def get_work_order(work_order_id: uuid.UUID, session: Session = Depends(get_session)) -> Any:
    return WorkOrderService(session).detail(work_order_id)


@router.patch("/work-orders/{work_order_id}", response_model=WorkOrderOut)
def update_work_order(
    work_order_id: uuid.UUID,
    data: WorkOrderUpdate,
    user: CurrentUser = planner,
    session: Session = Depends(get_session),
) -> Any:
    return WorkOrderService(session).update_order(user, work_order_id, data)


@router.post("/work-orders/{work_order_id}/close", response_model=WorkOrderOut)
def close_work_order(
    work_order_id: uuid.UUID,
    data: WorkOrderClose,
    user: CurrentUser = planner,
    service: WorkOrderService = Depends(work_order_service),
) -> Any:
    return service.close_order(user, work_order_id, data)


@router.get("/work-orders/{work_order_id}/risk", response_model=WorkOrderRiskOut, dependencies=[reader])
def work_order_risk(work_order_id: uuid.UUID, session: Session = Depends(get_session)) -> Any:
    return WorkOrderService(session).risk(work_order_id)


# ── Schedules ─────────────────────────────────────────────────────────


@router.post("/schedules/optimise", response_model=ScheduleDetail)
def optimise_schedule(
    data: OptimiseRequest, user: CurrentUser = writer, session: Session = Depends(get_session)
) -> Any:
    return ScheduleService(session).optimise(user, data)


@router.get("/schedules/active", response_model=ScheduleDetail | None, dependencies=[reader])
def active_schedule(session: Session = Depends(get_session)) -> Any:
    return ScheduleService(session).active()


@router.get("/schedules/{schedule_id}", response_model=ScheduleDetail, dependencies=[reader])
def get_schedule(schedule_id: uuid.UUID, session: Session = Depends(get_session)) -> Any:
    return ScheduleService(session).detail(schedule_id)


@router.patch("/schedules/{schedule_id}/items/{item_id}")
def patch_schedule_item(
    schedule_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ScheduleItemPatch,
    user: CurrentUser = writer,
    session: Session = Depends(get_session),
) -> Any:
    result = ScheduleService(session).patch_item(user, schedule_id, item_id, data)
    return {"item": ScheduleItemOut.model_validate(result["item"]), "conflicts": result["conflicts"]}
