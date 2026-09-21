"""Service layer for reporting (M10).

`request` records a queued report and hands it to the worker; `generate` is the worker's side, and
is deliberately callable inline so a test — or a caller with no broker — can produce a real file.

Archive layout is `data/reports/{yyyy}/{mm}/{id}.{ext}` (FR-RP-06). The path is derived from the
report's own id, so two reports can never collide and a file can always be traced back to its row.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.common.service import CrudService
from app.core.audit import ensure_user, write_audit
from app.core.config import Settings, get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.core.security import CurrentUser
from app.modules.reports import charts, render
from app.modules.reports import data as report_data
from app.modules.reports import summary as summary_lib
from app.modules.reports.models import Report, ReportSchedule
from app.modules.reports.repository import ReportRepository, ReportScheduleRepository
from app.modules.reports.schemas import ReportCreate, ScheduleCreate, ScheduleUpdate

log = logging.getLogger(__name__)

DEFAULT_WINDOWS = {
    "machine_health": timedelta(days=7),
    "weekly_maintenance": timedelta(days=7),
    "energy": timedelta(days=7),
    "benchmark": timedelta(days=30),
    "incident": timedelta(days=2),
}
# A technician sees the reports about the floor; commercial and model reports are not their business.
ROLE_VISIBLE_TYPES = {
    "technician": ("machine_health", "weekly_maintenance", "incident"),
    "manager": ("machine_health", "weekly_maintenance", "energy", "incident"),
}


class ReportService:
    entity = "reports"

    def __init__(self, session: Session, *, settings: Settings | None = None, archive_root: Path | None = None) -> None:
        self.session = session
        self.repo = ReportRepository(session)
        self.schedules = ReportScheduleRepository(session)
        self.settings = settings or get_settings()
        self.archive_root = archive_root or Path(self.settings.report_archive_dir)

    # ── Requesting ────────────────────────────────────────────────────

    def request(self, actor: CurrentUser | None, payload: ReportCreate, *, via: str = "ui") -> Report:
        """Record the request and enqueue it. Returns immediately; the worker fills in the file."""
        scope, scope_id = report_data.resolve_scope(self.session, payload.scope, payload.scope_id)
        end = payload.period_end or datetime.now(UTC)
        start = payload.period_start or end - DEFAULT_WINDOWS.get(payload.type, timedelta(days=7))
        if end <= start:
            raise UnprocessableError("period_end must be after period_start")

        report = Report(
            type=payload.type,
            scope=scope,
            scope_id=scope_id,
            period_start=start,
            period_end=end,
            format=payload.format,
            status="queued",
            requested_by=ensure_user(self.session, actor) if actor else None,
            requested_via=via,
        )
        self.session.add(report)
        self.session.flush()
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=report.id,
            action="create",
            after={"type": report.type, "format": report.format, "via": via},
        )
        self.session.commit()
        self._enqueue(report.id)
        return report

    def _enqueue(self, report_id: uuid.UUID) -> None:
        """Hand off to Celery; with no broker reachable the row stays queued rather than failing."""
        try:
            from app.workers.tasks.report import generate_report

            generate_report.delay(str(report_id))
        except Exception:
            log.warning("could not enqueue report %s; it remains queued", report_id, exc_info=True)

    # ── Reading ───────────────────────────────────────────────────────

    def get_or_404(self, report_id: uuid.UUID) -> Report:
        report = self.repo.get(report_id)
        if report is None:
            raise NotFoundError(f"Report {report_id} not found")
        return report

    def visible_types(self, actor: CurrentUser) -> tuple[str, ...] | None:
        """None means "everything"; engineers and admins see every type (FR-RP-06)."""
        if actor.has_any("engineer", "admin"):
            return None
        for role, types in ROLE_VISIBLE_TYPES.items():
            if actor.has_any(role):
                return types
        return ()

    def list_reports(
        self, actor: CurrentUser, params: PageParams, *, type_: str | None = None, status: str | None = None
    ) -> tuple[list[Report], int]:
        filters: list[ColumnElement[bool]] = []
        allowed = self.visible_types(actor)
        if allowed is not None:
            filters.append(Report.type.in_(allowed or ("__none__",)))
        if type_:
            filters.append(Report.type == type_)
        if status:
            filters.append(Report.status == status)
        return self.repo.list(params, filters)

    def file(self, actor: CurrentUser, report_id: uuid.UUID) -> tuple[bytes, str, str]:
        """(bytes, media type, download filename). 409 while it is still being produced."""
        report = self.get_or_404(report_id)
        allowed = self.visible_types(actor)
        if allowed is not None and report.type not in allowed:
            raise ForbiddenError("You do not have access to this report type")
        if report.status != "done" or not report.file_uri:
            raise ConflictError(f"That report is {report.status}")
        path = Path(report.file_uri)
        if not path.exists():
            raise NotFoundError("The report file is no longer in the archive")
        return (
            path.read_bytes(),
            render.MEDIA_TYPES.get(report.format, "application/octet-stream"),
            f"{report.type}-{report.created_at:%Y%m%d}-{str(report.id)[:8]}.{report.format}",
        )

    # ── Generating (the worker's side) ────────────────────────────────

    def generate(self, report_id: uuid.UUID) -> Report:
        """Assemble, summarise, audit, render and archive. Any failure lands on the report row."""
        report = self.get_or_404(report_id)
        if report.status == "done":
            return report
        report.status = "running"
        self.session.commit()

        try:
            figures = self._assemble(report)
            text, audit = summary_lib.compose(
                report.type, figures, endpoint=self.settings.llm_endpoint, model=self.settings.llm_model
            )
            context = render.build_context(
                report_id=str(report.id),
                report_type=report.type,
                scope_name=report_data.scope_name(self.session, report.scope, report.scope_id),
                period_start=report.period_start,
                period_end=report.period_end,
                generated_at=datetime.now(UTC),
                data=figures,
                charts=charts.for_report(report.type, figures),
                summary_text=text,
                summary_audit=audit.to_dict(),
                llm_model=self.settings.llm_model,
            )
            content, produced = render.render(context, report.format)
            path = self._archive_path(report, produced)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

            report.data = figures
            report.summary_text = text
            report.summary_audit = audit.to_dict()
            report.format = produced
            report.file_uri = str(path)
            report.status = "done"
            report.error = None
        except Exception as exc:
            log.exception("report generation failed", extra={"report_id": str(report_id)})
            report.status = "failed"
            report.error = str(exc)[:2000]
        report.finished_at = datetime.now(UTC)
        self.session.commit()
        return report

    def _assemble(self, report: Report) -> dict[str, Any]:
        start, end = report.period_start, report.period_end
        scope_id = report.scope_id
        if start is None or end is None or scope_id is None:
            raise UnprocessableError("The report is missing its period or its scope")
        match report.type:
            case "machine_health":
                return report_data.machine_health(self.session, scope_id, start, end)
            case "weekly_maintenance":
                return report_data.weekly_maintenance(self.session, report.scope or "plant", scope_id, start, end)
            case "energy":
                return report_data.energy(self.session, report.scope or "plant", scope_id, start, end)
            case "benchmark":
                return report_data.benchmark(self.session, start, end)
            case "incident":
                at = report_data.latest_failure_at(self.session, scope_id) or end
                return report_data.incident(self.session, scope_id, at)
            case _:
                raise UnprocessableError(f"Unknown report type {report.type}")

    def _archive_path(self, report: Report, fmt: str) -> Path:
        created = report.created_at or datetime.now(UTC)
        return self.archive_root / f"{created:%Y}" / f"{created:%m}" / f"{report.id}.{fmt}"


class ReportScheduleService(CrudService[ReportSchedule]):
    entity = "report_schedules"
    label = "Report schedule"

    def __init__(self, session: Session) -> None:
        super().__init__(session, ReportScheduleRepository(session))

    def list_schedules(self, params: PageParams) -> tuple[list[ReportSchedule], int]:
        return self.repo.list(params)

    def create_schedule(self, actor: CurrentUser, payload: ScheduleCreate) -> ReportSchedule:
        return self.create(actor, ReportSchedule(**payload.model_dump()))

    def update_schedule(self, actor: CurrentUser, schedule_id: uuid.UUID, payload: ScheduleUpdate) -> ReportSchedule:
        schedule = self.get_or_404(schedule_id)
        return self.update(actor, schedule, payload.model_dump(exclude_unset=True))

    def delete_schedule(self, actor: CurrentUser, schedule_id: uuid.UUID) -> None:
        self.retire(actor, self.get_or_404(schedule_id))
