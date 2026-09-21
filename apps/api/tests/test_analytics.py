"""Unit tests for the M8 analytics engines: OEE, reliability, Pareto, energy baseline and anomalies.

These exercise the pure computation modules and need no database; the endpoints that wrap them are
covered by the API tests that run against the compose `postgres` service.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import pytest

from app.modules.analytics import energy, oee
from app.modules.analytics.repository import TariffRepository, _within

START = datetime(2026, 9, 19, 6, 0, tzinfo=UTC)
END = START + timedelta(hours=8)


def durations(*pairs: tuple[str, float], cause: str | None = None) -> list[oee.StateDuration]:
    return [oee.StateDuration(state=state, seconds=seconds, cause_code=cause) for state, seconds in pairs]


# ── Availability, performance, quality, OEE ───────────────────────────


def test_availability_excludes_planned_maintenance_from_planned_time():
    """Six hours running, one idle, one in planned maintenance: availability is 6/7, not 6/8."""
    result = oee.availability(durations(("RUNNING", 6 * 3600), ("IDLE", 3600), ("MAINTENANCE", 3600)))
    assert result.value == pytest.approx(85.714, abs=0.01)
    assert result.inputs["planned_time_s"] == 7 * 3600


def test_availability_with_no_planned_time_is_zero_not_a_crash():
    assert oee.availability([]).value == 0.0
    assert oee.availability(durations(("MAINTENANCE", 3600))).value == 0.0


def test_performance_is_capped_at_100_and_records_the_uncapped_value():
    """Producing faster than the configured ideal cycle means the ideal is wrong, not that P > 100."""
    result = oee.performance(run_time_s=3600, total_count=1000, ideal_cycle_time_s=10.0)
    assert result.value == 100.0
    assert result.inputs["uncapped"] == pytest.approx(277.778, abs=0.01)


def test_performance_without_an_ideal_cycle_time_says_why_it_is_zero():
    result = oee.performance(run_time_s=3600, total_count=100, ideal_cycle_time_s=None)
    assert result.value == 0.0
    assert "no ideal cycle time" in result.inputs["note"]


def test_quality_handles_a_period_with_no_production():
    assert oee.quality(0, 0).value == 0.0
    assert oee.quality(95, 100).value == 95.0


def test_oee_is_the_product_of_the_three_factors():
    assert oee.oee(90.0, 95.0, 99.0).value == pytest.approx(84.645, abs=0.001)
    assert oee.oee(100.0, 100.0, 100.0).value == 100.0


def test_compute_all_returns_every_kpi_with_its_inputs():
    results = {
        r.code: r
        for r in oee.compute_all(
            durations(("RUNNING", 6 * 3600), ("DOWN", 2 * 3600)),
            good_count=1900,
            reject_count=100,
            ideal_cycle_time_s=10.0,
            breakdown_count=2,
            repair_time_s=3600,
            repair_count=2,
        )
    }
    assert set(results) == {"availability", "performance", "quality", "oee", "mtbf", "mttr"}
    assert results["quality"].value == 95.0
    assert results["mtbf"].value == pytest.approx(3.0)  # 6 run hours / 2 breakdowns
    assert results["mttr"].value == pytest.approx(0.5)  # 1 repair hour / 2 repairs
    assert all(r.inputs for r in results.values())


def test_mtbf_with_no_breakdowns_reports_the_run_time_and_says_so():
    result = oee.mtbf(7200, 0)
    assert result.value == 2.0
    assert "no breakdowns" in result.inputs["note"]


def test_mttr_with_no_repairs_is_zero():
    assert oee.mttr(0.0, 0).value == 0.0


# ── State events -> durations ─────────────────────────────────────────


def test_durations_clip_an_event_that_started_before_the_period():
    """The machine went DOWN an hour before the shift; only the in-shift hour counts."""
    events = [(START - timedelta(hours=1), "DOWN", "breakdown"), (START + timedelta(hours=1), "RUNNING", None)]
    result = oee.durations_from_events(events, START, END)
    assert result[0].state == "DOWN"
    assert result[0].seconds == 3600
    assert result[1].seconds == 7 * 3600


def test_the_last_event_runs_to_the_end_of_the_period():
    result = oee.durations_from_events([(START, "RUNNING", None)], START, END)
    assert len(result) == 1
    assert result[0].seconds == 8 * 3600


def test_no_events_yields_no_durations():
    assert oee.durations_from_events([], START, END) == []


def test_events_are_sorted_before_being_paired():
    events = [(START + timedelta(hours=4), "IDLE", None), (START, "RUNNING", None)]
    result = oee.durations_from_events(events, START, END)
    assert [d.state for d in result] == ["RUNNING", "IDLE"]


# ── Downtime Pareto ───────────────────────────────────────────────────


def test_downtime_pareto_is_descending_with_a_cumulative_share():
    rows = oee.downtime_pareto(
        [
            oee.StateDuration("DOWN", 3600, "tool_change"),
            oee.StateDuration("DOWN", 7200, "breakdown"),
            oee.StateDuration("IDLE", 1800, None),
            oee.StateDuration("RUNNING", 9999, None),  # excluded: not downtime
        ]
    )
    assert [r["cause_code"] for r in rows] == ["breakdown", "tool_change", "unclassified"]
    assert rows[0]["share"] == pytest.approx(7200 / 12600, abs=0.001)
    assert rows[-1]["cumulative_share"] == pytest.approx(1.0)


def test_downtime_pareto_with_no_downtime():
    assert oee.downtime_pareto(durations(("RUNNING", 3600))) == []


# ── Energy baseline ───────────────────────────────────────────────────


def test_baseline_recovers_a_known_linear_relationship():
    points = [(float(units), 5.0 + 2.0 * units) for units in range(10)]
    baseline = energy.fit_baseline(points)
    assert baseline is not None
    assert baseline.intercept_kwh == pytest.approx(5.0, abs=1e-6)
    assert baseline.slope_kwh_per_unit == pytest.approx(2.0, abs=1e-6)
    assert baseline.r2 == pytest.approx(1.0)


def test_baseline_refuses_too_few_points():
    assert energy.fit_baseline([(float(i), float(i)) for i in range(4)]) is None


def test_baseline_refuses_a_period_where_output_never_varied():
    """A flat x gives an undefined slope, and a baseline fitted on it would flag noise forever."""
    assert energy.fit_baseline([(10.0, 20.0 + i) for i in range(12)]) is None


def test_anomaly_detection_is_one_sided():
    points = [(float(u), 5.0 + 2.0 * u + (0.3 if u % 2 else -0.3)) for u in range(20)]
    baseline = energy.fit_baseline(points)
    assert baseline is not None

    at = datetime(2026, 9, 19, 12, tzinfo=UTC)
    over = energy.find_anomalies(baseline, [(at, 10.0, 5.0 + 20.0 + 10.0)], scope_id="a")
    under = energy.find_anomalies(baseline, [(at, 10.0, 5.0 + 20.0 - 10.0)], scope_id="a")
    assert len(over) == 1
    assert over[0].sigma > 3.0
    assert under == []  # consuming less than expected is not an anomaly


def test_anomaly_detection_is_quiet_when_consumption_matches_the_baseline():
    points = [(float(u), 5.0 + 2.0 * u + (0.2 if u % 2 else -0.2)) for u in range(20)]
    baseline = energy.fit_baseline(points)
    assert baseline is not None
    at = datetime(2026, 9, 19, 12, tzinfo=UTC)
    assert energy.find_anomalies(baseline, [(at, 10.0, 25.1)], scope_id="a") == []


# ── Energy summary ────────────────────────────────────────────────────


def test_energy_summary_derives_co2_intensity_and_idle_share():
    summary = energy.summarise(
        energy_kwh=1000.0,
        idle_energy_kwh=150.0,
        peak_demand_kw=85.0,
        cost=8200.0,
        good_count=500,
        grid_emission_factor=0.716,
    )
    assert summary.co2_kg == pytest.approx(716.0)
    assert summary.energy_per_unit == pytest.approx(2.0)
    assert summary.idle_energy_share == pytest.approx(15.0)


def test_energy_summary_with_no_production_has_no_intensity():
    summary = energy.summarise(
        energy_kwh=100.0,
        idle_energy_kwh=100.0,
        peak_demand_kw=10.0,
        cost=800.0,
        good_count=0,
        grid_emission_factor=0.716,
    )
    assert summary.energy_per_unit is None
    assert summary.idle_energy_share == 100.0


def test_energy_summary_with_no_energy_does_not_divide_by_zero():
    summary = energy.summarise(
        energy_kwh=0.0,
        idle_energy_kwh=0.0,
        peak_demand_kw=0.0,
        cost=0.0,
        good_count=0,
        grid_emission_factor=0.716,
    )
    assert summary.idle_energy_share == 0.0
    assert summary.co2_kg == 0.0


def test_energy_kpi_results_omit_intensity_when_there_is_no_output():
    without = energy.as_kpi_results(
        energy.summarise(
            energy_kwh=10.0,
            idle_energy_kwh=1.0,
            peak_demand_kw=5.0,
            cost=1.0,
            good_count=0,
            grid_emission_factor=0.7,
        )
    )
    assert {r.code for r in without} == {"idle_energy_share", "peak_demand"}


# ── Tariff windows ────────────────────────────────────────────────────


class FakeTariff:
    def __init__(self, start: time, end: time, rate: float, days: list[int]) -> None:
        self.starts_local, self.ends_local = start, end
        self.rate_per_kwh, self.days_of_week = rate, days


def test_tariff_window_wrapping_past_midnight():
    assert _within(time(23, 0), time(22, 0), time(6, 0)) is True
    assert _within(time(2, 0), time(22, 0), time(6, 0)) is True
    assert _within(time(12, 0), time(22, 0), time(6, 0)) is False


def test_tariff_rate_picks_the_window_in_force():
    tariffs = [
        FakeTariff(time(6, 0), time(18, 0), 9.5, [0, 1, 2, 3, 4]),
        FakeTariff(time(18, 0), time(6, 0), 6.0, [0, 1, 2, 3, 4]),
    ]
    saturday = datetime(2026, 9, 19, 12, tzinfo=UTC)  # a Saturday: no tariff applies
    friday_noon = datetime(2026, 9, 18, 12, tzinfo=UTC)
    friday_night = datetime(2026, 9, 18, 23, tzinfo=UTC)

    assert TariffRepository.rate_at(tariffs, friday_noon) == 9.5
    assert TariffRepository.rate_at(tariffs, friday_night) == 6.0
    assert TariffRepository.rate_at(tariffs, saturday) == 0.0
    assert TariffRepository.rate_at([], friday_noon) == 0.0
