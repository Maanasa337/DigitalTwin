"""Report data assembly (FR-RP-01).

Every figure in a report comes from the module that owns it — OEE and energy from `analytics`, work
orders from `maintenance`, predictions and explanations from `pdm`/`xai`. Nothing is recomputed
here, so a number in a PDF and the same number on the dashboard cannot disagree.

The dict a builder returns is stored on `reports.data` and is the only input the narrative summary
is allowed to use, which is what makes the numeric audit (FR-RP-04) a closed check.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import UnprocessableError
from app.modules.analytics.service import EnergyService, KpiService
from app.modules.assets.models import Asset, Line, Plant
from app.modules.maintenance.models import Technician, WorkOrder
from app.modules.pdm.models import BenchmarkRun, Model, Prediction
from app.modules.telemetry.models import Alarm
from app.modules.xai.models import Explanation

INCIDENT_WINDOW = timedelta(hours=48)  # §M10.1: the timeline runs ±48 h around the failure


def scope_name(session: Session, scope: str | None, scope_id: uuid.UUID | None) -> str:
    if scope_id is None:
        plant = session.scalars(select(Plant).where(Plant.deleted_at.is_(None))).first()
        return plant.name if plant else "the plant"
    row: Line | Asset | None = session.get(Line, scope_id) if scope == "line" else session.get(Asset, scope_id)
    return row.name if row is not None else "the plant"


def resolve_scope(session: Session, scope: str | None, scope_id: uuid.UUID | None) -> tuple[str, uuid.UUID]:
    """A report always has a concrete scope; an unscoped request means the one plant."""
    if scope_id is not None:
        return scope or "asset", scope_id
    plant = session.scalars(select(Plant).where(Plant.deleted_at.is_(None))).first()
    if plant is None:
        raise UnprocessableError("No plant is configured yet")
    return "plant", plant.id


def _asset_ids(session: Session, scope: str, scope_id: uuid.UUID) -> list[uuid.UUID]:
    if scope == "asset":
        return [scope_id]
    stmt = select(Asset.id).where(Asset.deleted_at.is_(None))
    if scope == "line":
        return list(session.scalars(stmt.where(Asset.line_id == scope_id)))
    return list(session.scalars(stmt.join(Line, Line.id == Asset.line_id).where(Line.plant_id == scope_id)))


# ── Builders, one per report type ─────────────────────────────────────


def machine_health(session: Session, scope_id: uuid.UUID, start: datetime, end: datetime) -> dict[str, Any]:
    asset = session.get(Asset, scope_id)
    if asset is None:
        raise UnprocessableError("That machine is not in the registry")

    predictions = list(
        session.scalars(
            select(Prediction)
            .where(Prediction.asset_id == asset.id, Prediction.time >= start, Prediction.time < end)
            .order_by(Prediction.time)
        )
    )
    latest = predictions[-1] if predictions else None
    alarms = list(
        session.scalars(
            select(Alarm)
            .where(Alarm.asset_id == asset.id, Alarm.raised_at >= start, Alarm.raised_at < end)
            .order_by(Alarm.raised_at.desc())
        )
    )
    orders = list(
        session.scalars(
            select(WorkOrder)
            .where(WorkOrder.asset_id == asset.id, WorkOrder.created_at >= start, WorkOrder.deleted_at.is_(None))
            .order_by(WorkOrder.created_at.desc())
        )
    )
    oee = KpiService(session).oee(scope="asset", scope_id=asset.id, period="day", start=start, end=end)

    return {
        "asset": {"code": asset.code, "name": asset.name, "type": asset.asset_type, "status": asset.status},
        "health_pct": float(latest.health_index) if latest and latest.health_index is not None else None,
        "rul": latest.rul_point if latest else None,
        "rul_low": latest.rul_low if latest else None,
        "rul_high": latest.rul_high if latest else None,
        "rul_unit": (latest.rul_unit if latest else None) or "cycles",
        "confidence": latest.confidence_label if latest else None,
        "oee_pct": oee["oee"],
        "availability_pct": oee["availability"],
        "performance_pct": oee["performance"],
        "quality_pct": oee["quality"],
        "alarm_count": len(alarms),
        "open_work_orders": sum(1 for o in orders if o.status in ("open", "scheduled", "in_progress")),
        "health_series": [
            {"t": p.time.isoformat(), "health": float(p.health_index) if p.health_index is not None else None}
            for p in predictions
        ],
        "rul_series": [{"t": p.time.isoformat(), "rul": p.rul_point} for p in predictions if p.rul_point is not None],
        "alarms": [
            {"at": a.raised_at.isoformat(), "severity": a.severity, "title": a.title, "status": a.status}
            for a in alarms[:20]
        ],
        "work_orders": [_order_row(session, o) for o in orders[:20]],
    }


def weekly_maintenance(
    session: Session, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime
) -> dict[str, Any]:
    """Orders raised and closed in the week, plus how last week's predictions actually turned out."""
    asset_ids = _asset_ids(session, scope, scope_id)
    orders = list(
        session.scalars(
            select(WorkOrder)
            .where(
                WorkOrder.asset_id.in_(asset_ids),
                WorkOrder.created_at >= start,
                WorkOrder.created_at < end,
                WorkOrder.deleted_at.is_(None),
            )
            .order_by(WorkOrder.created_at)
        )
    )
    closed = list(
        session.scalars(
            select(WorkOrder).where(
                WorkOrder.asset_id.in_(asset_ids),
                WorkOrder.actual_end >= start,
                WorkOrder.actual_end < end,
                WorkOrder.deleted_at.is_(None),
            )
        )
    )
    scored = [o for o in closed if o.prediction_was_correct is not None]
    correct = sum(1 for o in scored if o.prediction_was_correct)
    reliability = KpiService(session).reliability(scope=scope, scope_id=scope_id, start=start, end=end)

    by_status: dict[str, int] = {}
    for order in orders:
        by_status[order.status] = by_status.get(order.status, 0) + 1

    return {
        "scope_name": scope_name(session, scope, scope_id),
        "raised": len(orders),
        "closed": len(closed),
        "by_status": by_status,
        "by_type": _count(orders, "type"),
        "predictions_scored": len(scored),
        "predictions_correct": correct,
        # None, not 0: "no prediction was checked" and "every prediction was wrong" are different facts.
        "prediction_accuracy_pct": round(100 * correct / len(scored), 1) if scored else None,
        "mtbf_h": reliability["mtbf_h"],
        "mttr_h": reliability["mttr_h"],
        "breakdowns": reliability["breakdowns"],
        "orders": [_order_row(session, o) for o in orders[:50]],
    }


def energy(session: Session, scope: str, scope_id: uuid.UUID, start: datetime, end: datetime) -> dict[str, Any]:
    service = EnergyService(session)
    summary = service.summary(scope=scope, scope_id=scope_id, start=start, end=end)
    anomalies = service.anomalies(scope=scope, scope_id=scope_id, start=start, end=end)
    return {
        "scope_name": scope_name(session, scope, scope_id),
        "energy_kwh": summary["energy_kwh"],
        "cost": summary["cost"],
        "currency": summary["currency"],
        "co2_kg": summary["co2_kg"],
        "peak_demand_kw": summary["peak_demand_kw"],
        "idle_energy_kwh": summary["idle_energy_kwh"],
        "idle_energy_share_pct": summary["idle_energy_share"],
        "energy_per_unit": summary["energy_per_unit"],
        "top_consumers": summary["breakdown"][:5],
        "intensity_trend": summary["intensity_trend"],
        "anomaly_count": len(anomalies),
        "anomalies": anomalies[:20],
    }


def benchmark(session: Session, start: datetime, end: datetime) -> dict[str, Any]:
    run = session.scalars(
        select(BenchmarkRun).where(BenchmarkRun.status == "done").order_by(BenchmarkRun.started_at.desc())
    ).first()
    models = list(session.scalars(select(Model).where(Model.stage == "production").order_by(Model.trained_at.desc())))
    return {
        "run": (
            {
                "started_at": run.started_at.isoformat(),
                "git_sha": run.git_sha,
                "seed": run.seed,
                "datasets": run.datasets,
                "results": run.results or {},
            }
            if run
            else None
        ),
        "production_models": [
            {
                "name": m.name,
                "version": m.version,
                "task": m.task,
                "algorithm": m.algorithm,
                "trained_at": m.trained_at.isoformat(),
            }
            for m in models
        ],
        "model_count": len(models),
    }


def incident(session: Session, asset_id: uuid.UUID, at: datetime) -> dict[str, Any]:
    """The 96-hour window around a failure: what was predicted, what was said, what was done."""
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise UnprocessableError("That machine is not in the registry")
    start, end = at - INCIDENT_WINDOW, at + INCIDENT_WINDOW

    predictions = list(
        session.scalars(
            select(Prediction)
            .where(Prediction.asset_id == asset_id, Prediction.time >= start, Prediction.time < end)
            .order_by(Prediction.time)
        )
    )
    explanations = {
        e.prediction_id: e
        for e in session.scalars(
            select(Explanation).where(Explanation.prediction_id.in_([p.id for p in predictions] or [uuid.uuid4()]))
        )
    }
    alarms = list(
        session.scalars(
            select(Alarm)
            .where(Alarm.asset_id == asset_id, Alarm.raised_at >= start, Alarm.raised_at < end)
            .order_by(Alarm.raised_at)
        )
    )
    orders = list(
        session.scalars(
            select(WorkOrder)
            .where(
                WorkOrder.asset_id == asset_id,
                WorkOrder.created_at >= start,
                WorkOrder.created_at < end,
                WorkOrder.deleted_at.is_(None),
            )
            .order_by(WorkOrder.created_at)
        )
    )

    timeline: list[dict[str, Any]] = []
    for prediction in predictions:
        explanation = explanations.get(prediction.id)
        timeline.append(
            {
                "at": prediction.time.isoformat(),
                "kind": "prediction",
                "detail": f"RUL {prediction.rul_point} {prediction.rul_unit or 'cycles'}",
                "top_driver": _top_driver(explanation),
                "recommended": (explanation.reason_card or {}).get("action") if explanation else None,
            }
        )
    timeline += [{"at": a.raised_at.isoformat(), "kind": "alarm", "detail": f"{a.severity}: {a.title}"} for a in alarms]
    timeline += [
        {
            "at": o.created_at.isoformat(),
            "kind": "work_order",
            "detail": f"#{o.number} {o.title} ({o.status})",
            "outcome": o.outcome,
        }
        for o in orders
    ]
    timeline.sort(key=lambda row: row["at"])

    return {
        "asset": {"code": asset.code, "name": asset.name},
        "failure_at": at.isoformat(),
        "window_hours": int(INCIDENT_WINDOW.total_seconds() // 3600),
        "prediction_count": len(predictions),
        "alarm_count": len(alarms),
        "work_order_count": len(orders),
        "recommended_actions": sorted({row["recommended"] for row in timeline if row.get("recommended")}),
        "actions_taken": [o.outcome for o in orders if o.outcome],
        "timeline": timeline,
    }


# ── Helpers ───────────────────────────────────────────────────────────


def _order_row(session: Session, order: WorkOrder) -> dict[str, Any]:
    technician = session.get(Technician, order.technician_id) if order.technician_id else None
    asset = session.get(Asset, order.asset_id)
    return {
        "number": order.number,
        "asset": asset.name if asset else "",
        "title": order.title,
        "type": order.type,
        "priority": order.priority,
        "status": order.status,
        "planned_start": order.planned_start.isoformat() if order.planned_start else None,
        "technician": technician.name if technician else None,
        "prediction_was_correct": order.prediction_was_correct,
    }


def _top_driver(explanation: Explanation | None) -> str | None:
    if explanation is None or not explanation.attributions:
        return None
    top = min(explanation.attributions, key=lambda a: a.get("rank", 99))
    return top.get("label") or top.get("feature")


def _count(rows: list[Any], attribute: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = getattr(row, attribute)
        counts[key] = counts.get(key, 0) + 1
    return counts


def latest_failure_at(session: Session, asset_id: uuid.UUID) -> datetime | None:
    """An incident report says "the press failure"; this is which one that was."""
    return session.scalar(
        select(func.max(Alarm.raised_at)).where(Alarm.asset_id == asset_id, Alarm.severity.in_(("critical", "high")))
    )
