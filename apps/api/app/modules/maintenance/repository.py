"""Repository layer for maintenance scheduling (M7)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, select, update
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.common.repository import CrudRepository
from app.modules.maintenance.models import (
    OPEN_STATUSES,
    Schedule,
    ScheduleItem,
    Technician,
    TechnicianAvailability,
    WorkOrder,
    WorkOrderTask,
)


class TechnicianRepository(CrudRepository[Technician]):
    model = Technician
    sortable = frozenset({"created_at", "code", "name"})
    default_sort = "code"

    def by_code(self, code: str) -> Technician | None:
        return self.session.scalars(self._select().where(Technician.code == code)).first()

    def availability(self, technician_id: uuid.UUID, start: datetime, end: datetime) -> list[TechnicianAvailability]:
        return list(
            self.session.scalars(
                select(TechnicianAvailability)
                .where(
                    TechnicianAvailability.technician_id == technician_id,
                    TechnicianAvailability.ends_at > start,
                    TechnicianAvailability.starts_at < end,
                )
                .order_by(TechnicianAvailability.starts_at)
            )
        )

    def add_availability(self, row: TechnicianAvailability) -> TechnicianAvailability:
        self.session.add(row)
        self.session.flush()
        return row


class WorkOrderRepository(CrudRepository[WorkOrder]):
    model = WorkOrder
    sortable = frozenset({"created_at", "number", "priority", "planned_start", "status"})
    default_sort = "-created_at"

    def list_filtered(
        self,
        params: PageParams,
        *,
        asset_id: uuid.UUID | None = None,
        status: str | None = None,
        type_: str | None = None,
        technician_id: uuid.UUID | None = None,
        open_only: bool = False,
    ) -> tuple[list[WorkOrder], int]:
        filters: list[ColumnElement[bool]] = []
        if asset_id:
            filters.append(WorkOrder.asset_id == asset_id)
        if status:
            filters.append(WorkOrder.status == status)
        if type_:
            filters.append(WorkOrder.type == type_)
        if technician_id:
            filters.append(WorkOrder.technician_id == technician_id)
        if open_only:
            filters.append(WorkOrder.status.in_(OPEN_STATUSES))
        return self.list(params, filters)

    def open_for_mode(self, asset_id: uuid.UUID, failure_mode_id: uuid.UUID) -> WorkOrder | None:
        return self.session.scalars(
            self._select().where(
                WorkOrder.asset_id == asset_id,
                WorkOrder.failure_mode_id == failure_mode_id,
                WorkOrder.status.in_(OPEN_STATUSES),
            )
        ).first()

    def schedulable(self, asset_ids: list[uuid.UUID] | None = None) -> list[WorkOrder]:
        """Orders the optimiser may place: open or already scheduled, never started or closed."""
        stmt = self._select().where(WorkOrder.status.in_(("open", "scheduled")))
        if asset_ids:
            stmt = stmt.where(WorkOrder.asset_id.in_(asset_ids))
        return list(self.session.scalars(stmt.order_by(WorkOrder.priority, WorkOrder.created_at)))

    def tasks(self, work_order_id: uuid.UUID) -> list[WorkOrderTask]:
        return list(
            self.session.scalars(
                select(WorkOrderTask)
                .where(WorkOrderTask.work_order_id == work_order_id)
                .order_by(WorkOrderTask.sequence)
            )
        )

    def add_tasks(self, tasks: list[WorkOrderTask]) -> None:
        self.session.add_all(tasks)
        self.session.flush()


class ScheduleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, schedule_id: uuid.UUID) -> Schedule | None:
        return self.session.get(Schedule, schedule_id)

    def active(self) -> Schedule | None:
        return self.session.scalars(select(Schedule).where(Schedule.is_active.is_(True))).first()

    def create(self, schedule: Schedule) -> Schedule:
        self.session.add(schedule)
        self.session.flush()
        return schedule

    def activate(self, schedule: Schedule) -> None:
        """Deactivate the previous plan first: a partial-unique index allows only one active row."""
        self.session.execute(
            update(Schedule).where(Schedule.is_active.is_(True), Schedule.id != schedule.id).values(is_active=False)
        )
        self.session.flush()
        schedule.is_active = True
        self.session.flush()

    def items(self, schedule_id: uuid.UUID) -> list[ScheduleItem]:
        return list(
            self.session.scalars(
                select(ScheduleItem).where(ScheduleItem.schedule_id == schedule_id).order_by(ScheduleItem.starts_at)
            )
        )

    def item(self, item_id: uuid.UUID) -> ScheduleItem | None:
        return self.session.get(ScheduleItem, item_id)

    def add_items(self, items: list[ScheduleItem]) -> None:
        self.session.add_all(items)
        self.session.flush()
