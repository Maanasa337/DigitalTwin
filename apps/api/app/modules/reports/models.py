"""ORM models for reporting (M10): generated reports and their cron schedules."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, PKMixin, SoftDeleteMixin, TimestampMixin

REPORT_TYPES = ("machine_health", "weekly_maintenance", "energy", "benchmark", "incident")
# `html` is what the renderer stores when WeasyPrint's native libraries are missing, so it is a real
# delivered format rather than a failure — the report still opens, it just is not paginated.
REPORT_FORMATS = ("pdf", "docx", "md", "html")
REPORT_STATUSES = ("queued", "running", "done", "failed")
REQUESTED_VIA = ("ui", "voice", "chat", "schedule", "event")

ACTIVE = text("deleted_at IS NULL")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(v) for v in values)})"


class ReportSchedule(PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "report_schedules"
    __table_args__ = (
        CheckConstraint(_in("type", REPORT_TYPES), name="type"),
        CheckConstraint(_in("format", REPORT_FORMATS), name="format"),
        Index("ix_report_schedules_enabled", "enabled", postgresql_where=ACTIVE),
    )

    type: Mapped[str]
    scope: Mapped[str | None]
    scope_id: Mapped[uuid.UUID | None]
    format: Mapped[str]
    cron: Mapped[str]
    recipients: Mapped[list[str]] = mapped_column(server_default=text("'{}'"))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    last_run_at: Mapped[datetime | None]


class Report(PKMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(_in("type", REPORT_TYPES), name="type"),
        CheckConstraint(_in("format", REPORT_FORMATS), name="format"),
        CheckConstraint(_in("status", REPORT_STATUSES), name="status"),
        CheckConstraint("period_end is null or period_end > period_start", name="period"),
        Index("ix_reports_type_created_at", "type", text("created_at desc")),
        Index("ix_reports_status", "status"),
    )

    type: Mapped[str]
    scope: Mapped[str | None]
    scope_id: Mapped[uuid.UUID | None]
    period_start: Mapped[datetime | None]
    period_end: Mapped[datetime | None]
    format: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="queued")
    file_uri: Mapped[str | None]
    summary_text: Mapped[str | None] = mapped_column(Text)
    summary_audit: Mapped[dict[str, Any] | None]
    # The assembled figures, kept so a re-render (another format, a repeated read-back) reuses the
    # numbers the summary was audited against rather than recomputing a slightly different set.
    data: Mapped[dict[str, Any] | None]
    error: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    requested_via: Mapped[str] = mapped_column(server_default="ui")
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("report_schedules.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
