"""Unit tests for the M7 scheduling engine: Weibull risk model and the CP-SAT optimiser.

No database: these cover the parts that decide *when* work happens, which is where the scheduling
bugs live. The CRUD and closure endpoints are covered by the API tests against compose `postgres`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.maintenance import optimiser, risk

NOW = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)


def order(
    order_id: str,
    *,
    duration_min: int = 60,
    line_id: str = "line-1",
    skills: list[str] | None = None,
    risk_by_slot: list[float] | None = None,
    priority: int = 3,
    **kwargs: object,
) -> optimiser.OrderInput:
    return optimiser.OrderInput(
        id=order_id,
        asset_id=f"asset-{order_id}",
        line_id=line_id,
        duration_min=duration_min,
        priority=priority,
        required_skills=skills or [],
        risk_by_slot=risk_by_slot or [],
        **kwargs,  # type: ignore[arg-type]
    )


def technician(
    tech_id: str, *, skills: list[str] | None = None, slots: list[bool] | None = None
) -> optimiser.TechnicianInput:
    return optimiser.TechnicianInput(id=tech_id, skills=skills or [], available_slots=slots or [])


# ── Weibull risk model ────────────────────────────────────────────────


def test_weibull_median_equals_the_rul_point_estimate():
    """By construction P(failure by the point estimate) is 0.5 — that is what 'median life' means."""
    weibull = risk.fit_weibull(100.0, 80.0, 125.0)
    assert weibull.cdf(100.0) == pytest.approx(0.5, abs=1e-9)


def test_a_wider_interval_produces_a_fatter_early_tail():
    """Two assets with the same expected life: the less certain one is riskier to defer."""
    tight = risk.fit_weibull(100.0, 95.0, 105.0)
    wide = risk.fit_weibull(100.0, 20.0, 500.0)
    assert wide.shape < tight.shape
    assert wide.cdf(20.0) > tight.cdf(20.0)


def test_missing_interval_falls_back_to_an_ordinary_wear_out_shape():
    assert risk.fit_weibull(100.0, None, None).shape == 4.0


def test_risk_before_grows_with_how_long_the_slot_is_deferred():
    kwargs = {"rul_point": 100.0, "rul_low": 60.0, "rul_high": 160.0, "now": NOW, "rul_unit": "hours"}
    soon = risk.risk_before(slot_start=NOW + timedelta(hours=10), **kwargs)  # type: ignore[arg-type]
    later = risk.risk_before(slot_start=NOW + timedelta(hours=90), **kwargs)  # type: ignore[arg-type]
    assert 0.0 < soon < later < 1.0


def test_risk_is_zero_without_a_rul_and_for_a_slot_in_the_past():
    assert risk.risk_before(rul_point=None, rul_low=None, rul_high=None, now=NOW, slot_start=NOW) == 0.0
    assert (
        risk.risk_before(rul_point=10.0, rul_low=5.0, rul_high=15.0, now=NOW, slot_start=NOW - timedelta(hours=5))
        == 0.0
    )


def test_risk_delta_shows_the_cost_of_moving_the_slot_either_way():
    result = risk.risk_delta(
        rul_point=100.0,
        rul_low=60.0,
        rul_high=160.0,
        now=NOW,
        slot_start=NOW + timedelta(hours=48),
        rul_unit="hours",
    )
    assert result["risk_earlier"] < result["risk"] < result["risk_later"]
    assert result["shift_hours"] == 24.0


# ── Slot arithmetic ───────────────────────────────────────────────────


def test_slot_count_and_slot_time_round_trip():
    assert optimiser.slot_count(NOW, NOW + timedelta(hours=8)) == 32  # 8h / 15min
    assert optimiser.slot_time(NOW, 4) == NOW + timedelta(hours=1)


def test_slot_count_never_returns_zero():
    assert optimiser.slot_count(NOW, NOW + timedelta(minutes=5)) == 1


# ── Optimiser ─────────────────────────────────────────────────────────


def test_no_orders_solves_trivially():
    result = optimiser.solve([], [technician("t1")], n_slots=32, tariff_per_slot=[])
    assert result.status == "OPTIMAL"
    assert result.assignments == []


def test_no_technicians_leaves_everything_unscheduled():
    result = optimiser.solve([order("wo-1")], [], n_slots=32, tariff_per_slot=[])
    assert result.assignments == []
    assert result.unscheduled == ["wo-1"]


def test_every_order_gets_exactly_one_technician_and_one_slot():
    result = optimiser.solve(
        [order("wo-1"), order("wo-2", line_id="line-2")],
        [technician("t1"), technician("t2")],
        n_slots=32,
        tariff_per_slot=[],
    )
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert len(result.assignments) == 2
    assert all(a.technician_id is not None for a in result.assignments)
    assert all(a.end_slot > a.start_slot for a in result.assignments)


def test_orders_on_the_same_line_never_overlap():
    """Two jobs on one line must queue: the line cannot be down twice at once."""
    result = optimiser.solve(
        [order("wo-1", duration_min=120), order("wo-2", duration_min=120)],
        [technician("t1"), technician("t2")],
        n_slots=32,
        tariff_per_slot=[],
    )
    first, second = sorted(result.assignments, key=lambda a: a.start_slot)
    assert first.end_slot <= second.start_slot


def test_one_technician_cannot_do_two_jobs_at_once():
    result = optimiser.solve(
        [order("wo-1", line_id="line-1"), order("wo-2", line_id="line-2")],
        [technician("t1")],
        n_slots=32,
        tariff_per_slot=[],
    )
    first, second = sorted(result.assignments, key=lambda a: a.start_slot)
    assert first.technician_id == second.technician_id == "t1"
    assert first.end_slot <= second.start_slot


def test_skills_are_respected():
    result = optimiser.solve(
        [order("wo-1", skills=["electrical"])],
        [technician("t-mech", skills=["hydraulic"]), technician("t-elec", skills=["electrical"])],
        n_slots=32,
        tariff_per_slot=[],
    )
    assert result.assignments[0].technician_id == "t-elec"


def test_an_order_nobody_is_skilled_for_is_reported_unscheduled():
    result = optimiser.solve(
        [order("wo-1", skills=["nuclear"])],
        [technician("t1", skills=["hydraulic"])],
        n_slots=32,
        tariff_per_slot=[],
    )
    assert result.unscheduled == ["wo-1"]
    assert result.assignments == []


def test_an_order_longer_than_the_horizon_is_unscheduled_not_truncated():
    result = optimiser.solve([order("wo-1", duration_min=600)], [technician("t1")], n_slots=8, tariff_per_slot=[])
    assert result.unscheduled == ["wo-1"]


def test_technician_availability_windows_are_honoured():
    """t1 is only free in the last hour, so nothing may start before slot 28."""
    slots = [False] * 28 + [True] * 4
    result = optimiser.solve(
        [order("wo-1", duration_min=60)], [technician("t1", slots=slots)], n_slots=32, tariff_per_slot=[]
    )
    assert result.assignments[0].start_slot == 28


def test_rising_failure_risk_pulls_the_order_earlier():
    """Risk climbing with every slot should push the solver to the front of the horizon."""
    rising = [i / 32.0 for i in range(32)]
    result = optimiser.solve(
        [order("wo-1", duration_min=60, risk_by_slot=rising, failure_cost=1_000_000.0)],
        [technician("t1")],
        n_slots=32,
        tariff_per_slot=[],
        weights=optimiser.Weights(downtime_cost=0, failure_risk=1, energy_cost=0),
    )
    assert result.assignments[0].start_slot == 0


def test_a_cheap_tariff_window_pulls_the_order_into_it_when_risk_is_flat():
    """With no risk pressure, energy cost decides: slots 16-19 are an order of magnitude cheaper."""
    tariffs = [10.0] * 32
    tariffs[16:20] = [0.5] * 4
    result = optimiser.solve(
        [order("wo-1", duration_min=60, energy_kw=100.0, risk_by_slot=[0.0] * 32)],
        [technician("t1")],
        n_slots=32,
        tariff_per_slot=tariffs,
        weights=optimiser.Weights(downtime_cost=0, failure_risk=0, energy_cost=1),
    )
    assert result.assignments[0].start_slot == 16
    assert result.assignments[0].energy_cost == pytest.approx(0.5 * 100.0 * 1.0, abs=0.01)


def test_higher_priority_orders_are_scheduled_first():
    result = optimiser.solve(
        [
            order("wo-low", duration_min=60, priority=5, downtime_cost_per_hour=1000.0),
            order("wo-high", duration_min=60, priority=1, downtime_cost_per_hour=1000.0),
        ],
        [technician("t1")],
        n_slots=32,
        tariff_per_slot=[],
    )
    by_id = {a.order_id: a for a in result.assignments}
    assert by_id["wo-high"].start_slot < by_id["wo-low"].start_slot


def test_conflicts_detects_an_overlap_a_manual_drag_introduced():
    orders = {"wo-1": order("wo-1"), "wo-2": order("wo-2")}  # both on line-1
    overlapping = [
        optimiser.Assignment("wo-1", "t1", 0, 8, 0.0, 0.0),
        optimiser.Assignment("wo-2", "t2", 4, 12, 0.0, 0.0),
    ]
    found = optimiser.conflicts(overlapping, orders)
    assert len(found) == 1
    assert found[0]["kind"] == "line"


def test_conflicts_reports_a_double_booked_technician():
    orders = {"wo-1": order("wo-1", line_id="line-1"), "wo-2": order("wo-2", line_id="line-2")}
    found = optimiser.conflicts(
        [
            optimiser.Assignment("wo-1", "t1", 0, 8, 0.0, 0.0),
            optimiser.Assignment("wo-2", "t1", 4, 12, 0.0, 0.0),
        ],
        orders,
    )
    assert found[0]["kind"] == "technician"


def test_no_conflicts_when_nothing_overlaps():
    orders = {"wo-1": order("wo-1"), "wo-2": order("wo-2")}
    assert (
        optimiser.conflicts(
            [optimiser.Assignment("wo-1", "t1", 0, 4, 0.0, 0.0), optimiser.Assignment("wo-2", "t1", 4, 8, 0.0, 0.0)],
            orders,
        )
        == []
    )


def test_solve_stays_within_its_time_budget():
    """Twelve orders across three lines still has to answer inside the 10 s the UI waits."""
    orders = [order(f"wo-{i}", line_id=f"line-{i % 3}", duration_min=60) for i in range(12)]
    result = optimiser.solve(
        orders, [technician(f"t{i}") for i in range(4)], n_slots=96, tariff_per_slot=[], timeout_s=10.0
    )
    assert result.solve_ms < 12_000
    assert result.status in ("OPTIMAL", "FEASIBLE")
