"""REST endpoints for production and energy analytics (M8)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.common.pagination import PageParams, page_params
from app.common.schemas import Page
from app.core.db import get_session
from app.core.errors import UnprocessableError
from app.core.security import WRITE_ROLES, CurrentUser, get_current_user, require_role
from app.modules.analytics.models import Shift, Tariff
from app.modules.analytics.schemas import (
    BaselineCreate,
    BaselineOut,
    DowntimeParetoOut,
    EnergyAnomalyOut,
    EnergySummaryOut,
    KpiDefinitionOut,
    KpiSeriesOut,
    OeeOut,
    Period,
    ProductionPlanOut,
    ReliabilityOut,
    Scope,
    ShiftCreate,
    ShiftOut,
    TariffCreate,
    TariffOut,
)
from app.modules.analytics.service import EnergyService, KpiService, ShiftService, TariffService

router = APIRouter(tags=["analytics"])
reader = Depends(get_current_user)
writer = Depends(require_role(*WRITE_ROLES))

MAX_WINDOW_DAYS = 366


def _window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """One guard for every range endpoint: a reversed or year-plus window scans the whole hypertable."""
    if end <= start:
        raise UnprocessableError("'to' must be after 'from'")
    if (end - start).days > MAX_WINDOW_DAYS:
        raise UnprocessableError(f"The window cannot exceed {MAX_WINDOW_DAYS} days")
    return start, end


# ── KPIs ──────────────────────────────────────────────────────────────


@router.get("/kpis/definitions", response_model=list[KpiDefinitionOut], dependencies=[reader])
def kpi_definitions(session: Session = Depends(get_session)) -> Any:
    return KpiService(session).definitions()


@router.get("/kpis", response_model=list[KpiSeriesOut], dependencies=[reader])
def kpis(
    scope: Scope = "asset",
    id_: uuid.UUID = Query(..., alias="id"),
    period: Period = "day",
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    codes: str | None = Query(None, description="Comma-separated KPI codes"),
    session: Session = Depends(get_session),
) -> Any:
    start, end = _window(start, end)
    return KpiService(session).series(
        scope=scope,
        scope_id=id_,
        period=period,
        start=start,
        end=end,
        codes=[c.strip() for c in codes.split(",")] if codes else None,
    )


@router.get("/oee", response_model=OeeOut, dependencies=[reader])
def oee(
    scope: Scope = "asset",
    id_: uuid.UUID = Query(..., alias="id"),
    period: Period = "day",
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    session: Session = Depends(get_session),
) -> Any:
    start, end = _window(start, end)
    return KpiService(session).oee(scope=scope, scope_id=id_, period=period, start=start, end=end)


@router.get("/reliability", response_model=ReliabilityOut, dependencies=[reader])
def reliability(
    scope: Scope = "asset",
    id_: uuid.UUID = Query(..., alias="id"),
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    session: Session = Depends(get_session),
) -> Any:
    start, end = _window(start, end)
    return KpiService(session).reliability(scope=scope, scope_id=id_, start=start, end=end)


@router.get("/downtime/pareto", response_model=DowntimeParetoOut, dependencies=[reader])
def downtime_pareto(
    scope: Scope = "asset",
    id_: uuid.UUID = Query(..., alias="id"),
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    session: Session = Depends(get_session),
) -> Any:
    start, end = _window(start, end)
    return KpiService(session).downtime_pareto(scope=scope, scope_id=id_, start=start, end=end)


@router.get("/production/plan", response_model=ProductionPlanOut, dependencies=[reader])
def production_vs_plan(
    scope: Scope = "asset",
    id_: uuid.UUID = Query(..., alias="id"),
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    session: Session = Depends(get_session),
) -> Any:
    start, end = _window(start, end)
    return KpiService(session).production_vs_plan(scope=scope, scope_id=id_, start=start, end=end)


# ── Energy ────────────────────────────────────────────────────────────


@router.get("/energy/summary", response_model=EnergySummaryOut, dependencies=[reader])
def energy_summary(
    scope: Scope = "asset",
    id_: uuid.UUID = Query(..., alias="id"),
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    session: Session = Depends(get_session),
) -> Any:
    start, end = _window(start, end)
    return EnergyService(session).summary(scope=scope, scope_id=id_, start=start, end=end)


@router.get("/energy/anomalies", response_model=list[EnergyAnomalyOut], dependencies=[reader])
def energy_anomalies(
    scope: Scope = "asset",
    id_: uuid.UUID = Query(..., alias="id"),
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    session: Session = Depends(get_session),
) -> Any:
    start, end = _window(start, end)
    return EnergyService(session).anomalies(scope=scope, scope_id=id_, start=start, end=end)


@router.post("/energy/baselines", response_model=BaselineOut, status_code=status.HTTP_201_CREATED)
def create_baseline(data: BaselineCreate, user: CurrentUser = writer, session: Session = Depends(get_session)) -> Any:
    return EnergyService(session).create_baseline(user, data)


# ── Shifts and tariffs ────────────────────────────────────────────────


@router.get("/shifts", response_model=Page[ShiftOut], dependencies=[reader])
def list_shifts(
    plant_id: uuid.UUID | None = None,
    params: PageParams = Depends(page_params),
    session: Session = Depends(get_session),
) -> Any:
    items, total = ShiftService(session).repo.list(params, [Shift.plant_id == plant_id] if plant_id else [])
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.post("/shifts", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
def create_shift(data: ShiftCreate, user: CurrentUser = writer, session: Session = Depends(get_session)) -> Any:
    return ShiftService(session).create_shift(user, data)


@router.get("/tariffs", response_model=Page[TariffOut], dependencies=[reader])
def list_tariffs(
    plant_id: uuid.UUID | None = None,
    params: PageParams = Depends(page_params),
    session: Session = Depends(get_session),
) -> Any:
    items, total = TariffService(session).repo.list(params, [Tariff.plant_id == plant_id] if plant_id else [])
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.post("/tariffs", response_model=TariffOut, status_code=status.HTTP_201_CREATED)
def create_tariff(data: TariffCreate, user: CurrentUser = writer, session: Session = Depends(get_session)) -> Any:
    return TariffService(session).create_tariff(user, data)
