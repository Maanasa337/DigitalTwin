"""Maintenance schedule optimiser (FR-MS-02, FR-EN-05).

CP-SAT over 15-minute slots. Decides when each open work order runs and who runs it, minimising
downtime cost + failure risk cost + energy cost at the slot's tariff.

Costs are integers in paise/cents because CP-SAT is an integer solver; every float that enters the
objective is scaled once, here, so the reported objective_value is comparable across runs.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

log = logging.getLogger(__name__)

SLOT_MINUTES = 15
COST_SCALE = 100  # objective terms are currency * 100, i.e. paise
SOLVE_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class OrderInput:
    id: str
    asset_id: str
    line_id: str
    duration_min: int
    priority: int
    required_skills: list[str] = field(default_factory=list)
    downtime_cost_per_hour: float = 0.0
    failure_cost: float = 0.0
    # risk_by_slot[i] is P(failure before slot i) — precomputed by risk.risk_before.
    risk_by_slot: list[float] = field(default_factory=list)
    energy_kw: float = 0.0


@dataclass(frozen=True)
class TechnicianInput:
    id: str
    skills: list[str] = field(default_factory=list)
    hourly_cost: float = 0.0
    # available_slots[i] is True when this technician can work slot i.
    available_slots: list[bool] = field(default_factory=list)


@dataclass(frozen=True)
class Weights:
    downtime_cost: float = 1.0
    failure_risk: float = 1.0
    energy_cost: float = 1.0


@dataclass(frozen=True)
class Assignment:
    order_id: str
    technician_id: str | None
    start_slot: int
    end_slot: int
    risk_before: float
    energy_cost: float


@dataclass(frozen=True)
class SolveResult:
    status: str
    assignments: list[Assignment]
    objective_value: float | None
    solve_ms: int
    unscheduled: list[str] = field(default_factory=list)


def slot_count(horizon_start: datetime, horizon_end: datetime) -> int:
    return max(1, int((horizon_end - horizon_start).total_seconds() // (SLOT_MINUTES * 60)))


def slot_time(horizon_start: datetime, slot: int) -> datetime:
    return horizon_start + timedelta(minutes=SLOT_MINUTES * slot)


def solve(
    orders: list[OrderInput],
    technicians: list[TechnicianInput],
    *,
    n_slots: int,
    tariff_per_slot: list[float],
    weights: Weights | None = None,
    timeout_s: float = SOLVE_TIMEOUT_S,
) -> SolveResult:
    """Assign every order a start slot and a technician, or report it unscheduled.

    Constraints: technician availability, skill match, one order per line at a time, one order per
    technician at a time, and the whole order inside the horizon.
    """
    from ortools.sat.python import cp_model

    weights = weights or Weights()
    started = time.perf_counter()

    if not orders:
        return SolveResult(status="OPTIMAL", assignments=[], objective_value=0.0, solve_ms=0)
    if not technicians:
        return SolveResult(
            status="INFEASIBLE",
            assignments=[],
            objective_value=None,
            solve_ms=int((time.perf_counter() - started) * 1000),
            unscheduled=[o.id for o in orders],
        )

    model = cp_model.CpModel()
    durations = {o.id: max(1, -(-o.duration_min // SLOT_MINUTES)) for o in orders}

    starts: dict[str, Any] = {}
    intervals: dict[str, Any] = {}
    assigned: dict[tuple[str, str], Any] = {}

    for order in orders:
        duration = durations[order.id]
        if duration > n_slots:
            continue
        start = model.new_int_var(0, n_slots - duration, f"start_{order.id}")
        starts[order.id] = start
        intervals[order.id] = model.new_interval_var(start, duration, start + duration, f"iv_{order.id}")

        eligible = [t for t in technicians if _can_do(t, order)]
        if not eligible:
            continue
        literals = []
        for technician in eligible:
            literal = model.new_bool_var(f"assign_{order.id}_{technician.id}")
            assigned[(order.id, technician.id)] = literal
            literals.append(literal)
            # An order may only start where its technician is free for its whole duration.
            for slot in range(n_slots - duration + 1):
                if not all(_available(technician, slot + k) for k in range(duration)):
                    model.add(start != slot).only_enforce_if(literal)
        model.add_exactly_one(literals)

    schedulable = [o for o in orders if o.id in starts and any((o.id, t.id) in assigned for t in technicians)]
    unscheduled = [o.id for o in orders if o not in schedulable]

    # One order at a time per technician, and per production line.
    for technician in technicians:
        optional = [
            model.new_optional_interval_var(
                starts[o.id],
                durations[o.id],
                starts[o.id] + durations[o.id],
                assigned[(o.id, technician.id)],
                f"opt_{o.id}_{technician.id}",
            )
            for o in schedulable
            if (o.id, technician.id) in assigned
        ]
        if optional:
            model.add_no_overlap(optional)

    for line_id in {o.line_id for o in schedulable}:
        line_intervals = [intervals[o.id] for o in schedulable if o.line_id == line_id]
        if len(line_intervals) > 1:
            model.add_no_overlap(line_intervals)

    objective: list[Any] = []
    for order in schedulable:
        duration = durations[order.id]
        hours = duration * SLOT_MINUTES / 60.0

        # Downtime and labour cost do not depend on when the order runs, but a higher-priority order
        # is charged more for waiting, which is what pulls it earlier.
        wait_penalty = int(weights.downtime_cost * order.downtime_cost_per_hour * (6 - order.priority) * COST_SCALE)
        if wait_penalty:
            objective.append(wait_penalty * starts[order.id])

        # Risk and energy are slot-dependent, so they enter through one indicator per start slot.
        for slot in range(n_slots - duration + 1):
            is_start = model.new_bool_var(f"start_{order.id}_at_{slot}")
            model.add(starts[order.id] == slot).only_enforce_if(is_start)
            model.add(starts[order.id] != slot).only_enforce_if(is_start.negated())

            risk = order.risk_by_slot[slot] if slot < len(order.risk_by_slot) else 0.0
            energy = sum(
                order.energy_kw * (SLOT_MINUTES / 60.0) * _tariff(tariff_per_slot, slot + k) for k in range(duration)
            )
            cost = int((weights.failure_risk * risk * order.failure_cost + weights.energy_cost * energy) * COST_SCALE)
            if cost:
                objective.append(cost * is_start)

        for technician in technicians:
            assignment = assigned.get((order.id, technician.id))
            if assignment is not None and technician.hourly_cost:
                objective.append(int(technician.hourly_cost * hours * COST_SCALE) * assignment)

    if objective:
        model.minimize(sum(objective))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_s
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    solve_ms = int((time.perf_counter() - started) * 1000)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(
            status=status_name,
            assignments=[],
            objective_value=None,
            solve_ms=solve_ms,
            unscheduled=[o.id for o in orders],
        )

    assignments = []
    for order in schedulable:
        start_slot = solver.value(starts[order.id])
        duration = durations[order.id]
        technician_id = next(
            (t.id for t in technicians if (order.id, t.id) in assigned and solver.value(assigned[(order.id, t.id)])),
            None,
        )
        assignments.append(
            Assignment(
                order_id=order.id,
                technician_id=technician_id,
                start_slot=start_slot,
                end_slot=start_slot + duration,
                risk_before=order.risk_by_slot[start_slot] if start_slot < len(order.risk_by_slot) else 0.0,
                energy_cost=round(
                    sum(
                        order.energy_kw * (SLOT_MINUTES / 60.0) * _tariff(tariff_per_slot, start_slot + k)
                        for k in range(duration)
                    ),
                    2,
                ),
            )
        )

    return SolveResult(
        status=status_name,
        assignments=assignments,
        objective_value=solver.objective_value / COST_SCALE if objective else 0.0,
        solve_ms=solve_ms,
        unscheduled=unscheduled,
    )


def conflicts(assignments: list[Assignment], orders: dict[str, OrderInput]) -> list[dict[str, object]]:
    """Overlaps a manual drag can introduce — the solver's constraints stop applying once a human moves a bar."""
    found: list[dict[str, object]] = []
    ordered = sorted(assignments, key=lambda a: a.start_slot)
    for i, first in enumerate(ordered):
        for second in ordered[i + 1 :]:
            if second.start_slot >= first.end_slot:
                break
            same_technician = first.technician_id and first.technician_id == second.technician_id
            first_order, second_order = orders.get(first.order_id), orders.get(second.order_id)
            same_line = first_order and second_order and first_order.line_id == second_order.line_id
            if same_technician or same_line:
                found.append(
                    {
                        "orders": [first.order_id, second.order_id],
                        "kind": "technician" if same_technician else "line",
                    }
                )
    return found


def _can_do(technician: TechnicianInput, order: OrderInput) -> bool:
    return not order.required_skills or bool(set(order.required_skills) & set(technician.skills))


def _available(technician: TechnicianInput, slot: int) -> bool:
    if not technician.available_slots:
        return True  # no calendar recorded: treat the technician as always available
    return slot < len(technician.available_slots) and technician.available_slots[slot]


def _tariff(tariff_per_slot: list[float], slot: int) -> float:
    if not tariff_per_slot:
        return 0.0
    return tariff_per_slot[min(slot, len(tariff_per_slot) - 1)]
