"""OEE and reliability KPIs (FR-PA-01, FR-PA-02, FR-PA-03).

Every function returns the KPI value *and* the inputs it came from, because a KPI nobody can audit
is a KPI nobody acts on. Those inputs land in kpi_values.inputs and are what the UI shows on hover.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

RUNNING_STATES = ("RUNNING",)
DOWN_STATES = ("DOWN",)
IDLE_STATES = ("IDLE",)
# MAINTENANCE is planned, so it is excluded from planned production time rather than counted as loss.
UNPLANNED_STATES = ("DOWN", "IDLE", "UNKNOWN")


@dataclass(frozen=True)
class KpiResult:
    code: str
    value: float
    inputs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StateDuration:
    state: str
    seconds: float
    cause_code: str | None = None


def availability(durations: list[StateDuration]) -> KpiResult:
    """Run time over planned production time, as a percentage. Planned time excludes MAINTENANCE."""
    run_time = sum(d.seconds for d in durations if d.state in RUNNING_STATES)
    planned = sum(d.seconds for d in durations if d.state != "MAINTENANCE")
    value = 100.0 * run_time / planned if planned > 0 else 0.0
    return KpiResult(
        "availability",
        round(value, 3),
        {"run_time_s": round(run_time, 1), "planned_time_s": round(planned, 1)},
    )


def performance(run_time_s: float, total_count: int, ideal_cycle_time_s: float | None) -> KpiResult:
    """(ideal cycle * total count) / run time. Capped at 100: over-100 means the ideal cycle is wrong."""
    if not ideal_cycle_time_s or run_time_s <= 0:
        return KpiResult(
            "performance",
            0.0,
            {
                "run_time_s": round(run_time_s, 1),
                "total_count": total_count,
                "ideal_cycle_time_s": ideal_cycle_time_s,
                "note": "no ideal cycle time configured" if not ideal_cycle_time_s else "no run time in period",
            },
        )
    raw = 100.0 * (ideal_cycle_time_s * total_count) / run_time_s
    return KpiResult(
        "performance",
        round(min(raw, 100.0), 3),
        {
            "run_time_s": round(run_time_s, 1),
            "total_count": total_count,
            "ideal_cycle_time_s": ideal_cycle_time_s,
            "uncapped": round(raw, 3),
        },
    )


def quality(good_count: int, total_count: int) -> KpiResult:
    value = 100.0 * good_count / total_count if total_count > 0 else 0.0
    return KpiResult("quality", round(value, 3), {"good_count": good_count, "total_count": total_count})


def oee(availability_pct: float, performance_pct: float, quality_pct: float) -> KpiResult:
    """A * P * Q. The three factors are percentages, so divide out two of the hundreds."""
    value = availability_pct * performance_pct * quality_pct / 10_000.0
    return KpiResult(
        "oee",
        round(value, 3),
        {"availability": availability_pct, "performance": performance_pct, "quality": quality_pct},
    )


def mtbf(run_time_s: float, breakdown_count: int) -> KpiResult:
    """Mean time between failures, in hours. Undefined with no breakdowns — reported as the full run time."""
    if breakdown_count <= 0:
        return KpiResult(
            "mtbf",
            round(run_time_s / 3600.0, 3),
            {"run_time_s": round(run_time_s, 1), "breakdowns": 0, "note": "no breakdowns in period"},
        )
    return KpiResult(
        "mtbf",
        round(run_time_s / 3600.0 / breakdown_count, 3),
        {"run_time_s": round(run_time_s, 1), "breakdowns": breakdown_count},
    )


def mttr(repair_time_s: float, repair_count: int) -> KpiResult:
    if repair_count <= 0:
        return KpiResult("mttr", 0.0, {"repair_time_s": 0.0, "repairs": 0})
    return KpiResult(
        "mttr",
        round(repair_time_s / 3600.0 / repair_count, 3),
        {"repair_time_s": round(repair_time_s, 1), "repairs": repair_count},
    )


def downtime_pareto(durations: list[StateDuration], *, top_n: int = 10) -> list[dict[str, Any]]:
    """Downtime by cause, descending, with the running cumulative share (FR-PA-02)."""
    by_cause: dict[str, float] = {}
    for duration in durations:
        if duration.state not in UNPLANNED_STATES:
            continue
        by_cause[duration.cause_code or "unclassified"] = (
            by_cause.get(duration.cause_code or "unclassified", 0.0) + duration.seconds
        )

    total = sum(by_cause.values())
    rows = sorted(by_cause.items(), key=lambda item: item[1], reverse=True)[:top_n]
    out: list[dict[str, Any]] = []
    cumulative = 0.0
    for cause, seconds in rows:
        cumulative += seconds
        out.append(
            {
                "cause_code": cause,
                "seconds": round(seconds, 1),
                "share": round(seconds / total, 4) if total else 0.0,
                "cumulative_share": round(cumulative / total, 4) if total else 0.0,
            }
        )
    return out


def durations_from_events(
    events: list[tuple[datetime, str, str | None]], period_start: datetime, period_end: datetime
) -> list[StateDuration]:
    """Turn state-change events into durations clipped to the period.

    Each event holds until the next one. The last event runs to `period_end`, and an event that
    started before the period is clipped to `period_start` so its earlier time is not double-counted.
    """
    if not events:
        return []
    ordered = sorted(events, key=lambda e: e[0])
    out: list[StateDuration] = []
    for i, (at, state, cause) in enumerate(ordered):
        start = max(at, period_start)
        end = ordered[i + 1][0] if i + 1 < len(ordered) else period_end
        end = min(end, period_end)
        seconds = (end - start).total_seconds()
        if seconds > 0:
            out.append(StateDuration(state=state, seconds=seconds, cause_code=cause))
    return out


def compute_all(
    durations: list[StateDuration],
    *,
    good_count: int,
    reject_count: int,
    ideal_cycle_time_s: float | None,
    breakdown_count: int = 0,
    repair_time_s: float = 0.0,
    repair_count: int = 0,
) -> list[KpiResult]:
    """The full production KPI set for one scope and period, in one pass over the same inputs."""
    total_count = good_count + reject_count
    run_time_s = sum(d.seconds for d in durations if d.state in RUNNING_STATES)

    availability_result = availability(durations)
    performance_result = performance(run_time_s, total_count, ideal_cycle_time_s)
    quality_result = quality(good_count, total_count)
    return [
        availability_result,
        performance_result,
        quality_result,
        oee(availability_result.value, performance_result.value, quality_result.value),
        mtbf(run_time_s, breakdown_count),
        mttr(repair_time_s, repair_count),
    ]
