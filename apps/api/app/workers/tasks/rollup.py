"""Celery task: KPI rollup (FR-PA-01).

Runs hourly for the day in progress and at shift boundaries for the shift that just ended. The rollup
upserts, so re-running it for an open period refines the numbers instead of duplicating them.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.rollup.rollup_kpis", ignore_result=True)
def rollup_kpis(period: str = "day") -> int:
    """Roll up every plant, line and asset for the current period. Returns the number of KPI rows written."""
    from sqlalchemy import select

    from app.core.db import get_sessionmaker
    from app.modules.analytics.service import KpiService
    from app.modules.assets.models import Asset, Line, Plant

    written = 0
    with get_sessionmaker()() as session:
        plants = list(session.scalars(select(Plant).where(Plant.deleted_at.is_(None))))
        service = KpiService(session)

        for plant in plants:
            start, end = _period_bounds(session, plant, period)
            scopes: list[tuple[str, uuid.UUID]] = [("plant", plant.id)]
            scopes += [
                ("line", line.id)
                for line in session.scalars(select(Line).where(Line.plant_id == plant.id, Line.deleted_at.is_(None)))
            ]
            scopes += [
                ("asset", asset.id)
                for asset in session.scalars(
                    select(Asset)
                    .join(Line, Line.id == Asset.line_id)
                    .where(Line.plant_id == plant.id, Asset.deleted_at.is_(None))
                )
            ]

            for scope, scope_id in scopes:
                try:
                    written += service.rollup(scope=scope, scope_id=scope_id, period=period, start=start, end=end)
                except Exception:
                    log.exception("KPI rollup failed for %s %s", scope, scope_id)
                    session.rollback()

    if written:
        log.info("wrote %d KPI values for period '%s'", written, period)
    return written


@celery_app.task(name="app.workers.tasks.rollup.refresh_energy_baselines", ignore_result=True)
def refresh_energy_baselines(lookback_days: int = 30) -> int:
    """Refit each asset's energy baseline on the last `lookback_days` (FR-EN-02)."""
    from sqlalchemy import select

    from app.core.db import get_sessionmaker
    from app.modules.analytics.energy import fit_baseline
    from app.modules.analytics.models import EnergyBaseline
    from app.modules.analytics.repository import AnalyticsQueryRepository, BaselineRepository
    from app.modules.assets.models import Asset

    end = datetime.now(UTC)
    start = end - timedelta(days=lookback_days)
    refreshed = 0

    with get_sessionmaker()() as session:
        query = AnalyticsQueryRepository(session)
        baselines = BaselineRepository(session)
        for asset in session.scalars(select(Asset).where(Asset.deleted_at.is_(None))):
            observations = query.hourly_energy_and_output([asset.id], start, end)
            fitted = fit_baseline([(units, kwh) for _, units, kwh in observations])
            if fitted is None:
                continue
            baselines.create(
                EnergyBaseline(
                    scope="asset",
                    scope_id=asset.id,
                    period_start=start,
                    period_end=end,
                    intercept_kwh=fitted.intercept_kwh,
                    slope_kwh_per_unit=fitted.slope_kwh_per_unit,
                    r2=fitted.r2,
                )
            )
            refreshed += 1
        session.commit()
    return refreshed


def _period_bounds(session: Any, plant: Any, period: str) -> tuple[datetime, datetime]:
    """Bounds in the plant's own timezone — a 'day' means the plant's day, not UTC's."""
    tz = ZoneInfo(plant.timezone or "UTC")
    now_local = datetime.now(tz)

    if period == "shift":
        return _shift_bounds(session, plant, now_local, tz)
    if period == "week":
        start_local = (now_local - timedelta(days=now_local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return start_local.astimezone(UTC), (start_local + timedelta(days=7)).astimezone(UTC)
    if period == "month":
        start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (start_local + timedelta(days=32)).replace(day=1)
        return start_local.astimezone(UTC), next_month.astimezone(UTC)

    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(UTC), (start_local + timedelta(days=1)).astimezone(UTC)


def _shift_bounds(session: Any, plant: Any, now_local: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """The shift currently in progress; falls back to the calendar day when no shift is configured."""
    from app.modules.analytics.repository import ShiftRepository

    shifts = ShiftRepository(session).for_plant(plant.id)
    weekday = now_local.weekday()
    clock = now_local.time()

    for shift in shifts:
        if weekday not in (shift.days_of_week or []):
            continue
        if not _within(clock, shift.starts_local, shift.ends_local):
            continue
        start_local = datetime.combine(now_local.date(), shift.starts_local, tzinfo=tz)
        if shift.ends_local <= shift.starts_local:  # the shift crosses midnight
            if clock < shift.ends_local:
                start_local -= timedelta(days=1)
            end_local = start_local + timedelta(days=1)
            end_local = datetime.combine(end_local.date(), shift.ends_local, tzinfo=tz)
        else:
            end_local = datetime.combine(start_local.date(), shift.ends_local, tzinfo=tz)
        return start_local.astimezone(UTC), end_local.astimezone(UTC)

    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(UTC), (start_local + timedelta(days=1)).astimezone(UTC)


def _within(clock: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= clock < end
    return clock >= start or clock < end
