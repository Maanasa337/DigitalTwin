"""One function per intent (FR-NL-01), each one a thin call onto an existing module service.

The router never touches the database and the LLM never executes anything: an intent becomes a call
into `pdm`, `xai`, `telemetry`, `analytics`, `maintenance`, `reports` or `simulation`, and the dict
returned here is the only material the narrator is allowed to speak from (FR-NL-03).

Tools raise `ProblemError` subclasses. A T2 tool is only ever reached after its read-back was
confirmed and its parameters re-validated, so a tool body may assume the parameters exist.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cache
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session
from twinvoice_nlu import narrate

from app.core.errors import NotFoundError, UnprocessableError
from app.core.security import CurrentUser
from app.modules.analytics.service import EnergyService, KpiService
from app.modules.assets.models import Asset, Line
from app.modules.maintenance.schemas import WorkOrderCreate
from app.modules.maintenance.service import WorkOrderService
from app.modules.pdm.models import Model, Prediction
from app.modules.pdm.service import PredictionService
from app.modules.reports.schemas import ReportCreate
from app.modules.reports.service import ReportService
from app.modules.simulation.schemas import FaultInjection
from app.modules.simulation.service import SimulationService
from app.modules.telemetry.models import Alarm
from app.modules.telemetry.schemas import AlarmActionCreate
from app.modules.telemetry.service import AlarmService
from app.modules.twin.schemas import WhatIfRequest
from app.modules.xai.schemas import FeedbackCreate
from app.modules.xai.service import ExplanationService

# KPIs the analytics module computes as part of the OEE family; anything else is an energy figure.
PRODUCTION_KPIS = ("oee", "availability", "performance", "quality")
RELIABILITY_KPIS = ("mtbf", "mttr")
ENERGY_KPIS = ("energy_per_unit", "idle_energy_share", "peak_demand")

KPI_UNITS = {
    "oee": "percent", "availability": "percent", "performance": "percent", "quality": "percent",
    "mtbf": "hours", "mttr": "hours", "energy_per_unit": "kWh per unit",
    "idle_energy_share": "percent", "peak_demand": "kW",
}  # fmt: skip


class Publisher(Protocol):
    def __call__(self, channel: str, kind: str, payload: dict[str, Any]) -> None: ...


@dataclass
class ToolContext:
    session: Session
    actor: CurrentUser
    now: datetime
    lang: str = "en"
    session_id: uuid.UUID | None = None
    context: dict[str, Any] = field(default_factory=dict)
    simulator: Any = None
    publish: Publisher | None = None


# ── Shared lookups ────────────────────────────────────────────────────


def _asset(ctx: ToolContext, asset_id: Any) -> Asset:
    asset = ctx.session.get(Asset, _uuid(asset_id))
    if asset is None or asset.deleted_at is not None:
        raise NotFoundError("That machine is not in the registry")
    return asset


def _uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _latest_prediction(ctx: ToolContext, asset_id: uuid.UUID) -> Prediction | None:
    return PredictionService(ctx.session).latest(asset_id)


def _model_version(ctx: ToolContext, prediction: Prediction | None) -> str | None:
    if prediction is None:
        return None
    model = ctx.session.get(Model, prediction.model_id)
    return f"{model.name} v{model.version}" if model else None


def open_alarms(ctx: ToolContext, asset_id: uuid.UUID) -> list[Alarm]:
    return list(
        ctx.session.scalars(
            select(Alarm)
            .where(Alarm.asset_id == asset_id, Alarm.status.in_(("active", "acknowledged")))
            .order_by(Alarm.raised_at.desc())
        )
    )


def _top_driver(ctx: ToolContext, prediction: Prediction | None) -> tuple[str | None, uuid.UUID | None]:
    """The highest-ranked attribution of the latest explanation, which is what "the driver" means."""
    if prediction is None:
        return None, None
    explanation = ExplanationService(ctx.session).repo.by_prediction(prediction.id)
    if explanation is None or not explanation.attributions:
        return None, None
    top = min(explanation.attributions, key=lambda a: a.get("rank", 99))
    return top.get("label") or top.get("feature"), explanation.id


# ── T0 query tools ────────────────────────────────────────────────────


def get_machine_status(ctx: ToolContext, *, asset_id: Any, **_: Any) -> dict[str, Any]:
    asset = _asset(ctx, asset_id)
    prediction = _latest_prediction(ctx, asset.id)
    driver, explanation_id = _top_driver(ctx, prediction)
    alarms = open_alarms(ctx, asset.id)
    interval = (
        [prediction.rul_low, prediction.rul_high]
        if prediction and prediction.rul_low is not None and prediction.rul_high is not None
        else None
    )
    return {
        "asset": asset.name,
        "asset_code": asset.code,
        "asset_id": str(asset.id),
        "status": asset.status,
        "health_pct": float(prediction.health_index) if prediction and prediction.health_index else None,
        "rul": prediction.rul_point if prediction else None,
        "rul_unit": (prediction.rul_unit if prediction else None) or "cycles",
        "rul_interval": interval,
        "confidence": prediction.confidence_label if prediction else None,
        "top_driver": driver,
        "open_alarms": len(alarms),
        "at": prediction.time if prediction else None,
        "model_version": _model_version(ctx, prediction),
        "prediction_id": str(prediction.id) if prediction else None,
        "explanation_id": str(explanation_id) if explanation_id else None,
    }


def explain_prediction(ctx: ToolContext, *, asset_id: Any, **_: Any) -> dict[str, Any]:
    """Reuse the M6 narration pipeline, so a spoken "why" is the audited text the screen shows."""
    asset = _asset(ctx, asset_id)
    prediction = _latest_prediction(ctx, asset.id)
    if prediction is None:
        return {}
    service = ExplanationService(ctx.session)
    explanation = service.repo.by_prediction(prediction.id)
    if explanation is None:
        return {}
    narration, audit = service.narration(explanation.id, "why", ctx.lang)
    return {
        "asset": asset.name,
        "asset_code": asset.code,
        "narration": narration.final_text,
        "audit_passed": audit.passed if audit else None,
        "at": prediction.time,
        "model_version": _model_version(ctx, prediction),
        "prediction_id": str(prediction.id),
        "explanation_id": str(explanation.id),
    }


def get_counterfactual(ctx: ToolContext, *, asset_id: Any, **_: Any) -> dict[str, Any]:
    asset = _asset(ctx, asset_id)
    prediction = _latest_prediction(ctx, asset.id)
    if prediction is None:
        return {}
    service = ExplanationService(ctx.session)
    explanation = service.repo.by_prediction(prediction.id)
    if explanation is None:
        return {}
    rows = service.repo.counterfactuals(explanation.id)
    if not rows:
        return {}
    best = rows[0]
    return {
        "asset": asset.name,
        "asset_code": asset.code,
        "action_text": best.action_text,
        "changes": best.changes,
        "outcome": best.outcome,
        "feasibility": best.feasibility_score,
        "explanation_id": str(explanation.id),
        "at": prediction.time,
    }


def list_alarms(ctx: ToolContext, *, asset_id: Any = None, severity: str | None = None, **_: Any) -> dict[str, Any]:
    stmt = select(Alarm).where(Alarm.status.in_(("active", "acknowledged")))
    scope_label = "the plant"
    if asset_id is not None:
        asset = _asset(ctx, asset_id)
        stmt = stmt.where(Alarm.asset_id == asset.id)
        scope_label = asset.name
    if severity:
        stmt = stmt.where(Alarm.severity == severity)
    rows = list(ctx.session.scalars(stmt.order_by(Alarm.raised_at.desc()).limit(20)))
    order = {"critical": 0, "high": 1, "warning": 2, "info": 3}
    worst = sorted(rows, key=lambda a: order.get(a.severity, 9))[:3]
    return {
        "count": len(rows),
        "scope": scope_label,
        "severity": severity,
        "top": [f"{a.title} ({a.severity})" for a in worst],
        "alarm_ids": [str(a.id) for a in rows],
        "at": rows[0].raised_at if rows else None,
    }


def get_kpi(
    ctx: ToolContext,
    *,
    kpi: str,
    scope: str = "plant",
    scope_id: Any = None,
    period: str = "day",
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    **_: Any,
) -> dict[str, Any]:
    if scope_id is None:
        raise UnprocessableError("I need to know which line or machine you mean")
    start = period_start or (ctx.now - timedelta(days=1))
    end = period_end or ctx.now
    scope_id = _uuid(scope_id)
    value = _kpi_value(ctx, kpi, scope, scope_id, period, start, end)
    return {
        "kpi": kpi,
        "value": value,
        "unit": KPI_UNITS.get(kpi, ""),
        "scope": _scope_label(ctx, scope, scope_id),
        "scope_id": str(scope_id),
        "period": narrate.period_label(start, end),
        "from": start,
        "to": end,
        "at": end,
    }


def _kpi_value(
    ctx: ToolContext, kpi: str, scope: str, scope_id: uuid.UUID, period: str, start: datetime, end: datetime
) -> float | None:
    if kpi in PRODUCTION_KPIS:
        return KpiService(ctx.session).oee(scope=scope, scope_id=scope_id, period=period, start=start, end=end)[kpi]
    if kpi in RELIABILITY_KPIS:
        reliability = KpiService(ctx.session).reliability(scope=scope, scope_id=scope_id, start=start, end=end)
        return reliability[f"{kpi}_h"]
    summary = EnergyService(ctx.session).summary(scope=scope, scope_id=scope_id, start=start, end=end)
    return summary.get(kpi)


def _scope_label(ctx: ToolContext, scope: str, scope_id: uuid.UUID) -> str:
    row: Line | Asset | None = ctx.session.get(Line, scope_id) if scope == "line" else ctx.session.get(Asset, scope_id)
    return row.name if row is not None else "the plant"


def help_(ctx: ToolContext, **_: Any) -> dict[str, Any]:
    return {"ok": True}


# ── T1 simulate ───────────────────────────────────────────────────────


def run_what_if(
    ctx: ToolContext, *, asset_id: Any, parameter: str = "load", value: Any = None, **_: Any
) -> dict[str, Any]:
    """Project the RUL under a hypothetical by Monte-Carlo over the twin's own degradation state.

    Nothing is written and nothing is sent to the twin: T1 means the operator hears a number, not
    that the plant changed. Same engine as POST /twin/{code}/what-if, so the voice answer and the
    form answer cannot disagree.
    """
    from app.modules.twin.whatif_service import WhatIfService

    asset = _asset(ctx, asset_id)
    if ctx.simulator is None:
        raise UnprocessableError("The simulator is not available, so I cannot run a what-if.")

    request = _what_if_request(parameter, value, ctx.now)
    result = WhatIfService(ctx.session, ctx.simulator).run(asset, request)

    return {
        "asset": result.asset_name,
        "asset_code": result.asset_code,
        "change": _what_if_change(parameter, request),
        "baseline_rul": result.baseline.p50_h,
        "rul": result.hypothetical.p50_h,
        "rul_low": result.hypothetical.p10_h,
        "rul_high": result.hypothetical.p90_h,
        "rul_unit": "hours",
        "delta_rul": result.delta_p50_h,
        "failure_risk_before_service": result.hypothetical.risk_within_horizon,
        "baseline_risk": result.baseline.risk_within_horizon,
        "horizon_h": result.horizon_h,
        "trials": result.hypothetical.trials,
        "energy_delta_kwh": result.energy.delta_kwh,
        "energy_delta_cost": result.energy.delta_cost,
        "narrative": result.narrative,
        "at": ctx.now,
    }


def _what_if_request(parameter: str, value: Any, now: datetime) -> WhatIfRequest:
    """Map a spoken slot onto the what-if request the engine takes."""
    if parameter == "maintenance_at":
        when = value if isinstance(value, datetime) else None
        hours = (when - now).total_seconds() / 3600 if when else 168.0
        return WhatIfRequest(maintenance_in_h=max(hours, 0.0))

    pct = _percentage(value)
    if pct is None:
        raise UnprocessableError("I need a percentage, for example 'reduce load to 80 percent'")
    if parameter == "speed":
        return WhatIfRequest(speed_pct=pct)
    if parameter in ("ambient", "temperature"):
        return WhatIfRequest(ambient_c=pct)
    return WhatIfRequest(load_pct=pct)


def _what_if_change(parameter: str, request: WhatIfRequest) -> str:
    if request.maintenance_in_h is not None:
        return "servicing it then"
    for attr, label in (("load_pct", "load"), ("speed_pct", "speed"), ("ambient_c", "ambient")):
        setting = getattr(request, attr)
        if setting is not None:
            unit = " degrees" if attr == "ambient_c" else " percent"
            return f"{label} at {setting:.0f}{unit}"
    return parameter


def _percentage(value: Any) -> float | None:
    from twinvoice_nlu.slots import parse_number

    number = value if isinstance(value, int | float) else parse_number(str(value) if value else None)
    return float(number) if number and 0 < float(number) <= 200 else None


# ── T2 / T3 write tools ───────────────────────────────────────────────


def acknowledge_alarm(ctx: ToolContext, *, alarm_id: Any, **_: Any) -> dict[str, Any]:
    alarm = AlarmService(ctx.session).perform_action(
        ctx.actor, _uuid(alarm_id), AlarmActionCreate(action="ack", note="Acknowledged by voice")
    )
    asset = ctx.session.get(Asset, alarm.asset_id)
    return {
        "asset": asset.name if asset else "the asset",
        "asset_code": asset.code if asset else None,
        "alarm_id": str(alarm.id),
        "status": alarm.status,
        "at": alarm.acknowledged_at,
    }


def create_work_order(
    ctx: ToolContext,
    *,
    asset_id: Any,
    task: str,
    when: datetime | None = None,
    technician_id: Any = None,
    est_duration_min: int = 120,
    **_: Any,
) -> dict[str, Any]:
    asset = _asset(ctx, asset_id)
    order = WorkOrderService(ctx.session).create_order(
        ctx.actor,
        WorkOrderCreate(
            asset_id=asset.id,
            type="corrective",
            title=task[:200],
            description=f"Raised by voice: “{task}”",
            planned_start=when,
            planned_end=when + timedelta(minutes=est_duration_min) if when else None,
            technician_id=_uuid(technician_id) if technician_id else None,
            est_duration_min=est_duration_min,
            created_via="voice",
        ),
    )
    return {
        "asset": asset.name,
        "asset_code": asset.code,
        "number": order.number,
        "work_order_id": str(order.id),
        "status": order.status,
        "planned_start": order.planned_start,
        "at": order.created_at,
    }


def generate_report(
    ctx: ToolContext,
    *,
    type: str,
    scope: str = "plant",
    scope_id: Any = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    format: str = "pdf",
    **_: Any,
) -> dict[str, Any]:
    report = ReportService(ctx.session).request(
        ctx.actor,
        ReportCreate(
            type=type,
            scope=scope,
            scope_id=_uuid(scope_id) if scope_id else None,
            period_start=period_start,
            period_end=period_end,
            format=format,
        ),
        via="voice",
    )
    return {
        "type": report.type,
        "report_id": str(report.id),
        "status": report.status,
        "format": report.format,
        "at": report.created_at,
    }


def give_feedback(
    ctx: ToolContext, *, verdict: str = "disagree", reason: str | None = None, explanation_id: Any = None, **_: Any
) -> dict[str, Any]:
    if explanation_id is None:
        raise UnprocessableError("Ask me about a machine first, then tell me what the explanation got wrong")
    feedback = ExplanationService(ctx.session).add_feedback(
        ctx.actor,
        _uuid(explanation_id),
        FeedbackCreate(verdict=verdict, reason=reason, channel="voice"),
    )
    return {"verdict": feedback.verdict, "explanation_id": str(feedback.explanation_id), "at": feedback.created_at}


def set_simulation_scenario(
    ctx: ToolContext, *, scenario: str, asset_id: Any, severity: float = 0.5, **_: Any
) -> dict[str, Any]:
    if ctx.simulator is None:
        raise UnprocessableError("The simulator is not reachable from here")
    asset = _asset(ctx, asset_id)
    SimulationService(ctx.session, ctx.simulator).inject_fault(
        ctx.actor,
        FaultInjection(asset=asset.code, failure_mode=scenario.replace(" ", "_"), mode="gradual", severity=severity),
    )
    return {"scenario": scenario, "asset": asset.name, "asset_code": asset.code, "at": ctx.now}


# ── Navigation ────────────────────────────────────────────────────────


def navigate_dashboard(
    ctx: ToolContext, *, view: str | None = None, asset_id: Any = None, period: str | None = None, **_: Any
) -> dict[str, Any]:
    """Emit the WS event `uiStore` turns into a router push (FR-NL-05).

    A view named in the utterance outranks the asset carried in the dialogue context. Without that
    precedence, "show energy" said after "how is cnc one" opens the machine page instead of the
    energy page, because the asset is still in context and would otherwise win.
    """
    asset = _asset(ctx, asset_id) if asset_id is not None else None
    if view:
        path, label = view, _view_label(view)
    elif asset is not None:
        path, label = f"/machines/{asset.code}", asset.name
    else:
        path, label = "/", "the dashboard"

    payload = {
        "path": path,
        "label": label,
        "period": period,
        "asset_code": asset.code if asset is not None else None,
    }
    if ctx.publish and ctx.session_id:
        ctx.publish(f"voice:{ctx.session_id}", "navigate", payload)
    return {**payload, "at": ctx.now}


def _view_label(view: str) -> str:
    if view == "back":
        return "the previous screen"
    segment = view.rstrip("/").rsplit("/", 1)[-1]
    return segment.replace("-", " ").replace("_", " ") or "the fleet"


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_machine_status": get_machine_status,
    "explain_prediction": explain_prediction,
    "get_counterfactual": get_counterfactual,
    "run_what_if": run_what_if,
    "list_alarms": list_alarms,
    "acknowledge_alarm": acknowledge_alarm,
    "create_work_order": create_work_order,
    "get_kpi": get_kpi,
    "generate_report": generate_report,
    "set_simulation_scenario": set_simulation_scenario,
    "navigate_dashboard": navigate_dashboard,
    "give_feedback": give_feedback,
    "help": help_,
}


@cache
def required_arguments(intent: str) -> frozenset[str]:
    """Keyword-only parameters a tool has no default for — the ones that would raise a TypeError.

    Read off the signature rather than listed by hand, so a tool that grows a required parameter
    starts asking for it instead of failing the turn.
    """
    tool = TOOLS.get(intent)
    if tool is None:
        return frozenset()
    return frozenset(
        name
        for name, parameter in inspect.signature(tool).parameters.items()
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is inspect.Parameter.empty
    )
