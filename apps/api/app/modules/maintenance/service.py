"""Service layer for maintenance scheduling (M7)."""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.common.service import CrudService
from app.core.audit import ensure_user, snapshot, write_audit
from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.core.security import CurrentUser
from app.modules.assets.models import Asset
from app.modules.maintenance import optimiser, risk
from app.modules.maintenance.models import (
    Schedule,
    ScheduleItem,
    Technician,
    TechnicianAvailability,
    WorkOrder,
    WorkOrderTask,
)
from app.modules.maintenance.repository import ScheduleRepository, TechnicianRepository, WorkOrderRepository
from app.modules.maintenance.schemas import (
    AvailabilityCreate,
    OptimiseRequest,
    ScheduleItemPatch,
    TechnicianCreate,
    WorkOrderClose,
    WorkOrderCreate,
    WorkOrderUpdate,
)

DEFAULT_DURATION_MIN = 120
DEFAULT_DOWNTIME_COST_PER_HOUR = 5000.0
DEFAULT_FAILURE_COST = 200000.0
# A closed order must not be edited back open: the closure already published maintenance_reset.
TERMINAL_STATUSES = ("closed", "cancelled")


class TechnicianService(CrudService[Technician]):
    entity = "technicians"
    label = "Technician"

    def __init__(self, session: Session) -> None:
        super().__init__(session, TechnicianRepository(session))

    def create_technician(self, actor: CurrentUser, data: TechnicianCreate) -> Technician:
        if self.repo.by_code(data.code) is not None:  # type: ignore[attr-defined]
            raise ConflictError(f"Technician code '{data.code}' already exists")
        return self.create(actor, Technician(**data.model_dump()))

    def availability(self, technician_id: uuid.UUID, start: datetime, end: datetime) -> list[TechnicianAvailability]:
        self.get_or_404(technician_id)
        return self.repo.availability(technician_id, start, end)  # type: ignore[attr-defined]

    def add_availability(
        self, actor: CurrentUser, technician_id: uuid.UUID, data: AvailabilityCreate
    ) -> TechnicianAvailability:
        self.get_or_404(technician_id)
        row = self.repo.add_availability(  # type: ignore[attr-defined]
            TechnicianAvailability(technician_id=technician_id, **data.model_dump())
        )
        write_audit(
            self.session,
            actor=actor,
            entity="technician_availability",
            entity_id=row.id,
            action="create",
            after=snapshot(row),
        )
        self.session.commit()
        return row


class WorkOrderService(CrudService[WorkOrder]):
    entity = "work_orders"
    label = "Work order"

    def __init__(self, session: Session, commands: Any = None) -> None:
        super().__init__(session, WorkOrderRepository(session))
        self.commands = commands

    def list_orders(self, params: PageParams, **filters: Any) -> tuple[list[WorkOrder], int]:
        return self.repo.list_filtered(params, **filters)  # type: ignore[attr-defined]

    def detail(self, work_order_id: uuid.UUID) -> dict[str, Any]:
        order = self.get_or_404(work_order_id)
        asset = self.session.get(Asset, order.asset_id)
        technician = self.session.get(Technician, order.technician_id) if order.technician_id else None
        return {
            **{c.key: getattr(order, c.key) for c in order.__table__.columns},
            "asset_code": asset.code if asset else None,
            "technician_name": technician.name if technician else None,
            "tasks": self.repo.tasks(work_order_id),  # type: ignore[attr-defined]
        }

    def create_order(self, actor: CurrentUser | None, data: WorkOrderCreate) -> WorkOrder:
        if self.session.get(Asset, data.asset_id) is None:
            raise NotFoundError(f"Asset {data.asset_id} not found")

        payload = data.model_dump(exclude={"tasks"})
        order = WorkOrder(**payload, created_by=ensure_user(self.session, actor) if actor else None)
        self.repo.create(order)
        if data.tasks:
            self.repo.add_tasks(  # type: ignore[attr-defined]
                [WorkOrderTask(work_order_id=order.id, **task.model_dump()) for task in data.tasks]
            )
        write_audit(
            self.session, actor=actor, entity=self.entity, entity_id=order.id, action="create", after=snapshot(order)
        )
        self.session.commit()
        return order

    def update_order(self, actor: CurrentUser, work_order_id: uuid.UUID, data: WorkOrderUpdate) -> WorkOrder:
        order = self.get_or_404(work_order_id)
        if order.status in TERMINAL_STATUSES:
            raise ConflictError(f"Work order {order.number} is {order.status} and can no longer be edited")

        values = data.model_dump(exclude_unset=True)
        start = values.get("planned_start", order.planned_start)
        end = values.get("planned_end", order.planned_end)
        if start and end and end <= start:
            raise UnprocessableError("planned_end must be after planned_start")
        if values.get("technician_id") and self.session.get(Technician, values["technician_id"]) is None:
            raise NotFoundError(f"Technician {values['technician_id']} not found")
        return self.update(actor, order, values)

    def close_order(self, actor: CurrentUser, work_order_id: uuid.UUID, data: WorkOrderClose) -> WorkOrder:
        """Close the order and reset the simulated damage in the same transaction (FR-MS-05).

        The command goes out after the row is flushed but before the commit, so a rejected command
        rolls back the closure — an order marked done against a machine still carrying damage is the
        worse of the two failures.
        """
        order = self.get_or_404(work_order_id)
        if order.status == "closed":
            raise ConflictError(f"Work order {order.number} is already closed")
        if order.status == "cancelled":
            raise ConflictError(f"Work order {order.number} was cancelled and cannot be closed")

        before = snapshot(order)
        now = datetime.now(UTC)
        self.repo.update(
            order,
            {
                "status": "closed",
                "outcome": data.outcome,
                "actual_start": data.actual_start or order.actual_start or order.planned_start or now,
                "actual_end": data.actual_end or now,
                "prediction_was_correct": data.prediction_was_correct,
            },
        )

        if data.reset_damage and self.commands is not None:
            asset = self.session.get(Asset, order.asset_id)
            if asset is not None:
                self._reset_damage(asset.code, order, actor)

        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=order.id,
            action="close",
            before=before,
            after=snapshot(order),
        )
        self.session.commit()
        return order

    def _reset_damage(self, asset_code: str, order: WorkOrder, actor: CurrentUser) -> None:
        from app.core.errors import BadGatewayError

        _, reply = self.commands.execute(
            asset_code,
            "maintenance_reset",
            {"component_id": str(order.component_id) if order.component_id else None},
            issued_by=actor.sub,
            tier="T3",
            timeout_s=5.0,
        )
        if reply is not None and reply.get("status") not in (None, "accepted"):
            raise BadGatewayError(f"Simulator rejected maintenance reset: {reply.get('error') or reply['status']}")

    def risk(self, work_order_id: uuid.UUID) -> dict[str, Any]:
        """P(failure before the planned slot), plus what moving it ±24 h would do (FR-MS-04)."""
        from app.modules.pdm.repository import PredictionRepository

        order = self.get_or_404(work_order_id)
        prediction = PredictionRepository(self.session).latest(order.asset_id)
        now = datetime.now(UTC)
        slot = order.planned_start or now

        if prediction is None:
            return {
                "work_order_id": order.id,
                "planned_start": order.planned_start,
                "risk": 0.0,
                "risk_earlier": 0.0,
                "risk_later": 0.0,
                "shift_hours": 24.0,
            }
        return {
            "work_order_id": order.id,
            "planned_start": order.planned_start,
            **risk.risk_delta(
                rul_point=prediction.rul_point,
                rul_low=prediction.rul_low,
                rul_high=prediction.rul_high,
                now=now,
                slot_start=slot,
                rul_unit=prediction.rul_unit or "cycles",
            ),
            "rul_point": prediction.rul_point,
            "rul_low": prediction.rul_low,
            "rul_high": prediction.rul_high,
        }

    def export(self, fmt: str, **filters: Any) -> tuple[str, str, str]:
        """Return (content, media_type, filename) for CSV / JSON / B2MML-like XML (FR-MS-06)."""
        orders, _ = self.repo.list_filtered(PageParams(page=1, size=200, sort=None), **filters)  # type: ignore[attr-defined]
        rows = [
            {
                "number": o.number,
                "asset_id": str(o.asset_id),
                "type": o.type,
                "priority": o.priority,
                "title": o.title,
                "status": o.status,
                "planned_start": o.planned_start.isoformat() if o.planned_start else "",
                "planned_end": o.planned_end.isoformat() if o.planned_end else "",
                "technician_id": str(o.technician_id) if o.technician_id else "",
                "est_duration_min": o.est_duration_min or "",
                "outcome": o.outcome or "",
            }
            for o in orders
        ]

        if fmt == "json":
            return json.dumps(rows, indent=2), "application/json", "work-orders.json"
        if fmt == "b2mml":
            return _b2mml(rows), "application/xml", "work-orders.xml"

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]) if rows else ["number"])
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue(), "text/csv", "work-orders.csv"


class ScheduleService:
    entity = "schedules"

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ScheduleRepository(session)
        self.orders = WorkOrderRepository(session)
        self.technicians = TechnicianRepository(session)

    def get_or_404(self, schedule_id: uuid.UUID) -> Schedule:
        schedule = self.repo.get(schedule_id)
        if schedule is None:
            raise NotFoundError(f"Schedule {schedule_id} not found")
        return schedule

    def detail(self, schedule_id: uuid.UUID) -> dict[str, Any]:
        schedule = self.get_or_404(schedule_id)
        items = self.repo.items(schedule_id)
        return {
            **{c.key: getattr(schedule, c.key) for c in schedule.__table__.columns},
            "items": items,
            "unscheduled": [],
            "conflicts": self._conflicts(schedule, items),
        }

    def active(self) -> dict[str, Any] | None:
        schedule = self.repo.active()
        return self.detail(schedule.id) if schedule else None

    def optimise(self, actor: CurrentUser, request: OptimiseRequest) -> dict[str, Any]:
        """Run CP-SAT over the schedulable orders and persist the resulting plan."""
        orders = self.orders.schedulable(request.asset_ids or None)
        n_slots = optimiser.slot_count(request.horizon_start, request.horizon_end)
        now = datetime.now(UTC)

        order_inputs = [self._order_input(order, request.horizon_start, n_slots, now) for order in orders]
        technician_inputs = [
            self._technician_input(technician, request.horizon_start, n_slots) for technician in self.technicians.all()
        ]
        tariffs = self._tariff_per_slot(request.horizon_start, n_slots)

        result = optimiser.solve(
            order_inputs,
            technician_inputs,
            n_slots=n_slots,
            tariff_per_slot=tariffs,
            weights=optimiser.Weights(**request.weights.model_dump()),
        )

        schedule = self.repo.create(
            Schedule(
                horizon_start=request.horizon_start,
                horizon_end=request.horizon_end,
                objective=request.weights.model_dump(),
                solver_status=result.status,
                solve_ms=result.solve_ms,
                objective_value=result.objective_value,
            )
        )

        by_id = {str(o.id): o for o in orders}
        items = []
        for assignment in result.assignments:
            starts_at = optimiser.slot_time(request.horizon_start, assignment.start_slot)
            ends_at = optimiser.slot_time(request.horizon_start, assignment.end_slot)
            items.append(
                ScheduleItem(
                    schedule_id=schedule.id,
                    work_order_id=uuid.UUID(assignment.order_id),
                    technician_id=uuid.UUID(assignment.technician_id) if assignment.technician_id else None,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    risk_before=assignment.risk_before,
                    energy_cost=assignment.energy_cost,
                )
            )
            order = by_id[assignment.order_id]
            self.orders.update(
                order,
                {
                    "planned_start": starts_at,
                    "planned_end": ends_at,
                    "technician_id": items[-1].technician_id,
                    "risk_before_slot": assignment.risk_before,
                    "status": "scheduled" if order.status == "open" else order.status,
                },
            )
        self.repo.add_items(items)

        if request.activate and result.assignments:
            self.repo.activate(schedule)

        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=schedule.id,
            action="optimise",
            after={
                "solver_status": result.status,
                "objective_value": result.objective_value,
                "scheduled": len(result.assignments),
                "unscheduled": len(result.unscheduled),
            },
        )
        self.session.commit()

        return {
            **{c.key: getattr(schedule, c.key) for c in schedule.__table__.columns},
            "items": items,
            "unscheduled": [uuid.UUID(oid) for oid in result.unscheduled],
            "conflicts": [],
        }

    def patch_item(
        self, actor: CurrentUser, schedule_id: uuid.UUID, item_id: uuid.UUID, data: ScheduleItemPatch
    ) -> dict[str, Any]:
        """Apply a Gantt drag: re-score risk and cost, and report any conflict it creates.

        A manual move is never rejected — the planner may know something the solver does not — but it
        is flagged `manually_adjusted` and the conflicts it introduces are returned alongside it.
        """
        schedule = self.get_or_404(schedule_id)
        item = self.repo.item(item_id)
        if item is None or item.schedule_id != schedule_id:
            raise NotFoundError(f"Schedule item {item_id} not found in schedule {schedule_id}")

        before = snapshot(item)
        starts_at = data.starts_at or item.starts_at
        ends_at = data.ends_at or item.ends_at
        if data.starts_at and not data.ends_at:
            ends_at = starts_at + (item.ends_at - item.starts_at)
        if ends_at <= starts_at:
            raise UnprocessableError("ends_at must be after starts_at")
        if not (schedule.horizon_start <= starts_at and ends_at <= schedule.horizon_end):
            raise UnprocessableError("The new slot falls outside the schedule horizon")
        if data.technician_id and self.session.get(Technician, data.technician_id) is None:
            raise NotFoundError(f"Technician {data.technician_id} not found")

        order = self.session.get(WorkOrder, item.work_order_id)
        item.starts_at = starts_at
        item.ends_at = ends_at
        item.technician_id = data.technician_id if data.technician_id is not None else item.technician_id
        item.manually_adjusted = True
        item.risk_before = self._risk_at(order, starts_at) if order else item.risk_before
        self.session.flush()

        if order is not None:
            self.orders.update(
                order,
                {
                    "planned_start": starts_at,
                    "planned_end": ends_at,
                    "technician_id": item.technician_id,
                    "risk_before_slot": item.risk_before,
                },
            )

        write_audit(
            self.session,
            actor=actor,
            entity="schedule_items",
            entity_id=item.id,
            action="adjust",
            before=before,
            after=snapshot(item),
        )
        self.session.commit()

        items = self.repo.items(schedule_id)
        return {"item": item, "conflicts": self._conflicts(schedule, items)}

    # ── Optimiser inputs ──────────────────────────────────────────────

    def _order_input(
        self, order: WorkOrder, horizon_start: datetime, n_slots: int, now: datetime
    ) -> optimiser.OrderInput:
        from app.modules.pdm.repository import PredictionRepository

        asset = self.session.get(Asset, order.asset_id)
        prediction = PredictionRepository(self.session).latest(order.asset_id)
        risk_by_slot = [
            risk.risk_before(
                rul_point=prediction.rul_point if prediction else None,
                rul_low=prediction.rul_low if prediction else None,
                rul_high=prediction.rul_high if prediction else None,
                now=now,
                slot_start=optimiser.slot_time(horizon_start, slot),
                rul_unit=(prediction.rul_unit or "cycles") if prediction else "cycles",
            )
            for slot in range(n_slots)
        ]
        return optimiser.OrderInput(
            id=str(order.id),
            asset_id=str(order.asset_id),
            line_id=str(asset.line_id) if asset else str(order.asset_id),
            duration_min=order.est_duration_min or DEFAULT_DURATION_MIN,
            priority=order.priority,
            required_skills=[],
            downtime_cost_per_hour=DEFAULT_DOWNTIME_COST_PER_HOUR,
            failure_cost=float(order.est_cost or DEFAULT_FAILURE_COST),
            risk_by_slot=risk_by_slot,
            energy_kw=float(asset.rated_power_kw) if asset and asset.rated_power_kw else 0.0,
        )

    def _technician_input(
        self, technician: Technician, horizon_start: datetime, n_slots: int
    ) -> optimiser.TechnicianInput:
        horizon_end = optimiser.slot_time(horizon_start, n_slots)
        windows = self.technicians.availability(technician.id, horizon_start, horizon_end)
        if not windows:
            return optimiser.TechnicianInput(
                id=str(technician.id),
                skills=list(technician.skills or []),
                hourly_cost=float(technician.hourly_cost or 0),
                available_slots=[],
            )

        slots = [False] * n_slots
        for window in windows:
            if window.kind != "available":
                continue
            for slot in range(n_slots):
                slot_start = optimiser.slot_time(horizon_start, slot)
                if window.starts_at <= slot_start and slot_start < window.ends_at:
                    slots[slot] = True
        # Leave and training windows are subtracted after availability, so an overlapping leave wins.
        for window in windows:
            if window.kind == "available":
                continue
            for slot in range(n_slots):
                slot_start = optimiser.slot_time(horizon_start, slot)
                if window.starts_at <= slot_start < window.ends_at:
                    slots[slot] = False

        return optimiser.TechnicianInput(
            id=str(technician.id),
            skills=list(technician.skills or []),
            hourly_cost=float(technician.hourly_cost or 0),
            available_slots=slots,
        )

    def _tariff_per_slot(self, horizon_start: datetime, n_slots: int) -> list[float]:
        from app.modules.analytics.repository import TariffRepository

        tariffs = TariffRepository(self.session).all_active()
        if not tariffs:
            return []
        return [TariffRepository.rate_at(tariffs, optimiser.slot_time(horizon_start, slot)) for slot in range(n_slots)]

    def _risk_at(self, order: WorkOrder, slot_start: datetime) -> float:
        from app.modules.pdm.repository import PredictionRepository

        prediction = PredictionRepository(self.session).latest(order.asset_id)
        if prediction is None:
            return 0.0
        return risk.risk_before(
            rul_point=prediction.rul_point,
            rul_low=prediction.rul_low,
            rul_high=prediction.rul_high,
            now=datetime.now(UTC),
            slot_start=slot_start,
            rul_unit=prediction.rul_unit or "cycles",
        )

    def _conflicts(self, schedule: Schedule, items: list[ScheduleItem]) -> list[dict[str, Any]]:
        assignments = [
            optimiser.Assignment(
                order_id=str(item.work_order_id),
                technician_id=str(item.technician_id) if item.technician_id else None,
                start_slot=_slot_of(item.starts_at, schedule.horizon_start),
                end_slot=_slot_of(item.ends_at, schedule.horizon_start),
                risk_before=item.risk_before or 0.0,
                energy_cost=float(item.energy_cost or 0),
            )
            for item in items
        ]
        orders = {
            str(order.id): optimiser.OrderInput(
                id=str(order.id),
                asset_id=str(order.asset_id),
                line_id=str(self.session.get(Asset, order.asset_id).line_id)  # type: ignore[union-attr]
                if self.session.get(Asset, order.asset_id)
                else "",
                duration_min=order.est_duration_min or DEFAULT_DURATION_MIN,
                priority=order.priority,
            )
            for order in (self.session.get(WorkOrder, item.work_order_id) for item in items)
            if order is not None
        }
        return optimiser.conflicts(assignments, orders)


def _slot_of(at: datetime, horizon_start: datetime) -> int:
    return int((at - horizon_start).total_seconds() // (optimiser.SLOT_MINUTES * 60))


def _b2mml(rows: list[dict[str, Any]]) -> str:
    """A B2MML-shaped MaintenanceWorkRequest document. Not schema-validated — a template for import."""
    root = ET.Element("MaintenanceWorkRequestList", {"xmlns": "http://www.mesa.org/xml/B2MML-V0600"})
    for row in rows:
        request = ET.SubElement(root, "MaintenanceWorkRequest")
        ET.SubElement(request, "ID").text = f"WO-{row['number']:06d}"
        ET.SubElement(request, "Description").text = str(row["title"])
        ET.SubElement(request, "WorkType").text = str(row["type"])
        ET.SubElement(request, "Priority").text = str(row["priority"])
        ET.SubElement(request, "State").text = str(row["status"])
        schedule = ET.SubElement(request, "RequestedSchedule")
        ET.SubElement(schedule, "StartTime").text = str(row["planned_start"])
        ET.SubElement(schedule, "EndTime").text = str(row["planned_end"])
        ET.SubElement(request, "EquipmentID").text = str(row["asset_id"])
    return ET.tostring(root, encoding="unicode", xml_declaration=True)
