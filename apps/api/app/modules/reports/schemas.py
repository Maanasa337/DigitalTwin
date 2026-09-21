"""Pydantic schemas for reporting (M10)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.common.schemas import ORMModel

ReportType = Literal["machine_health", "weekly_maintenance", "energy", "benchmark", "incident"]
ReportFormat = Literal["pdf", "docx", "md", "html"]
ReportStatus = Literal["queued", "running", "done", "failed"]
Scope = Literal["plant", "line", "asset"]


class ReportCreate(BaseModel):
    type: ReportType
    scope: Scope | None = "plant"
    scope_id: uuid.UUID | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    format: ReportFormat = "pdf"

    @model_validator(mode="after")
    def _checks(self) -> ReportCreate:
        if self.period_start and self.period_end and self.period_end <= self.period_start:
            raise ValueError("period_end must be after period_start")
        if self.type in ("machine_health", "incident") and self.scope_id is None:
            raise ValueError(f"A {self.type.replace('_', ' ')} report needs an asset")
        return self


class ReportOut(ORMModel):
    id: uuid.UUID
    type: str
    scope: str | None
    scope_id: uuid.UUID | None
    period_start: datetime | None
    period_end: datetime | None
    format: str
    status: str
    file_uri: str | None
    summary_text: str | None
    summary_audit: dict[str, Any] | None
    error: str | None
    requested_by: uuid.UUID | None
    requested_via: str
    schedule_id: uuid.UUID | None
    created_at: datetime
    finished_at: datetime | None


class ReportDetail(ReportOut):
    data: dict[str, Any] | None = None


class ScheduleCreate(BaseModel):
    type: ReportType
    scope: Scope | None = "plant"
    scope_id: uuid.UUID | None = None
    format: ReportFormat = "pdf"
    # Standard five-field cron, evaluated by Celery beat in the plant's timezone.
    cron: str = Field(pattern=r"^(\S+\s+){4}\S+$")
    recipients: list[str] = Field(default_factory=list)
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    cron: str | None = Field(None, pattern=r"^(\S+\s+){4}\S+$")
    recipients: list[str] | None = None
    enabled: bool | None = None
    format: ReportFormat | None = None


class ScheduleOut(ORMModel):
    id: uuid.UUID
    type: str
    scope: str | None
    scope_id: uuid.UUID | None
    format: str
    cron: str
    recipients: list[str]
    enabled: bool
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
