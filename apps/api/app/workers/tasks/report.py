"""Celery tasks: report generation and the three triggers that raise one (FR-RP-03).

  on demand   `ReportService.request` enqueues `generate_report` directly
  scheduled   `run_report_schedules` runs every minute and fires the cron rows that are due
  event       `report_after_failure` / `report_after_order_closure` are called by the module that
              detected the event

Beat itself is not reconfigured when a schedule row changes: `run_report_schedules` evaluates the
crontab expressions against the wall clock instead, so adding a schedule through the API takes
effect without restarting the worker.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)

# A schedule that fires while the worker is down is run once when it comes back, not once per
# missed minute.
CATCHUP_WINDOW = timedelta(minutes=10)


@celery_app.task(name="app.workers.tasks.report.generate_report", ignore_result=True)
def generate_report(report_id: str) -> str:
    from app.core.db import get_sessionmaker
    from app.modules.reports.service import ReportService

    with get_sessionmaker()() as session:
        report = ReportService(session).generate(uuid.UUID(report_id))
        log.info("report generated", extra={"report_id": report_id, "status": report.status})
        return report.status


@celery_app.task(name="app.workers.tasks.report.run_report_schedules", ignore_result=True)
def run_report_schedules() -> int:
    """Fire every enabled schedule whose cron expression matches this minute. Returns how many."""
    from sqlalchemy import select

    from app.core.db import get_sessionmaker
    from app.modules.assets.models import Plant
    from app.modules.reports.repository import ReportScheduleRepository
    from app.modules.reports.schemas import ReportCreate
    from app.modules.reports.service import ReportService

    fired = 0
    with get_sessionmaker()() as session:
        plant = session.scalars(select(Plant).where(Plant.deleted_at.is_(None))).first()
        tz = ZoneInfo(plant.timezone) if plant else UTC
        now = datetime.now(tz)

        service = ReportService(session)
        repo = ReportScheduleRepository(session)
        for schedule in repo.enabled():
            if not _is_due(schedule.cron, now, schedule.last_run_at):
                continue
            service.request(
                None,
                ReportCreate(
                    type=schedule.type,
                    scope=schedule.scope,
                    scope_id=schedule.scope_id,
                    format=schedule.format,
                ),
                via="schedule",
            )
            repo.mark_run(schedule, now.astimezone(UTC))
            session.commit()
            fired += 1
    return fired


@celery_app.task(name="app.workers.tasks.report.report_after_failure", ignore_result=True)
def report_after_failure(asset_id: str) -> str | None:
    """Event trigger: a critical failure produces its incident report without anyone asking."""
    return _event_report(asset_id, "incident")


@celery_app.task(name="app.workers.tasks.report.report_after_order_closure", ignore_result=True)
def report_after_order_closure(asset_id: str) -> str | None:
    return _event_report(asset_id, "machine_health")


def _event_report(asset_id: str, report_type: str) -> str | None:
    from app.core.db import get_sessionmaker
    from app.modules.reports.schemas import ReportCreate
    from app.modules.reports.service import ReportService

    with get_sessionmaker()() as session:
        report = ReportService(session).request(
            None,
            ReportCreate(type=report_type, scope="asset", scope_id=uuid.UUID(asset_id), format="pdf"),
            via="event",
        )
        return str(report.id)


def _is_due(expression: str, now: datetime, last_run_at: datetime | None) -> bool:
    """True when `now` falls on a firing of this cron expression and it has not just fired.

    Celery parses the expression, so the syntax a user types is the syntax beat would accept;
    `last_run_at` suppresses the repeat a one-minute tick would otherwise cause, and also collapses
    the firings missed while the worker was down into a single catch-up run.
    """
    if not _matches(expression, now):
        return False
    if last_run_at is None:
        return True
    return now.astimezone(UTC) - last_run_at >= CATCHUP_WINDOW


def _matches(expression: str, now: datetime) -> bool:
    from celery.schedules import crontab

    minute, hour, day_of_month, month_of_year, day_of_week = expression.split()
    schedule = crontab(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
    )
    return (
        now.minute in schedule.minute
        and now.hour in schedule.hour
        # Celery numbers Sunday as 0, which is isoweekday() 7.
        and now.isoweekday() % 7 in schedule.day_of_week
        and now.day in schedule.day_of_month
        and now.month in schedule.month_of_year
    )
