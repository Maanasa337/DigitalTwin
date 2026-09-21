"""Repository layer for reporting (M10)."""

from __future__ import annotations

import builtins
import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, select

from app.common.repository import CrudRepository
from app.modules.reports.models import Report, ReportSchedule


class ReportRepository(CrudRepository[Report]):
    model = Report
    sortable = frozenset({"created_at", "type", "status", "finished_at"})
    default_sort = "-created_at"

    def recent(self, limit: int, filters: Sequence[ColumnElement[bool]] = ()) -> builtins.list[Report]:
        return list(
            self.session.scalars(select(Report).where(*filters).order_by(Report.created_at.desc()).limit(limit))
        )

    def latest_done(self, report_type: str, scope_id: uuid.UUID | None) -> Report | None:
        stmt = select(Report).where(Report.type == report_type, Report.status == "done")
        if scope_id is not None:
            stmt = stmt.where(Report.scope_id == scope_id)
        return self.session.scalars(stmt.order_by(Report.created_at.desc())).first()


class ReportScheduleRepository(CrudRepository[ReportSchedule]):
    model = ReportSchedule
    sortable = frozenset({"created_at", "type", "cron"})
    default_sort = "-created_at"

    def enabled(self) -> builtins.list[ReportSchedule]:
        return list(
            self.session.scalars(
                select(ReportSchedule).where(ReportSchedule.enabled.is_(True), ReportSchedule.deleted_at.is_(None))
            )
        )

    def mark_run(self, schedule: ReportSchedule, at: datetime) -> None:
        schedule.last_run_at = at
        self.session.flush()
