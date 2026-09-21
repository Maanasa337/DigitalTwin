"""Celery tasks for maintenance (M7): auto work-order creation and closure feedback.

Auto-creation (FR-MS-01) runs off the calibrated failure probability, never the raw one — an
uncalibrated 0.6 from a tree model is not a 60% chance, and raising work orders on it floods the
technicians' queue, which is exactly how a predictive-maintenance rollout loses trust.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)

DEFAULT_PROBABILITY_THRESHOLD = 0.6
PROBABILITY_THRESHOLDS: dict[str, float] = {
    "compressor": 0.55,
    "hydraulic_press": 0.65,
}
# Only act on a probability computed recently; a stale prediction says nothing about now.
MAX_PREDICTION_AGE_MIN = 30


@celery_app.task(name="app.workers.tasks.maintenance.raise_predictive_orders", ignore_result=True)
def raise_predictive_orders() -> int:
    """Open a predictive work order for every asset whose calibrated failure risk crossed its threshold."""
    from sqlalchemy import select

    from app.core.db import get_sessionmaker
    from app.modules.assets.models import Asset

    created = 0
    with get_sessionmaker()() as session:
        assets = list(session.scalars(select(Asset).where(Asset.deleted_at.is_(None))))
        for asset in assets:
            try:
                if _raise_for_asset(session, asset):
                    created += 1
            except Exception:
                log.exception("auto work-order check failed for asset %s", asset.code)
                session.rollback()
    if created:
        log.info("raised %d predictive work orders", created)
    return created


def _raise_for_asset(session: Any, asset: Any) -> bool:
    from sqlalchemy import select

    from app.modules.assets.models import FailureMode
    from app.modules.maintenance.repository import WorkOrderRepository
    from app.modules.maintenance.schemas import WorkOrderCreate
    from app.modules.maintenance.service import WorkOrderService
    from app.modules.pdm.repository import PredictionRepository
    from app.modules.xai.repository import ExplanationRepository, KnowledgeBaseRepository

    prediction = PredictionRepository(session).latest(asset.id)
    if prediction is None:
        return False
    age = datetime.now(UTC) - _as_utc(prediction.time)
    if age > timedelta(minutes=MAX_PREDICTION_AGE_MIN):
        return False

    probabilities = prediction.failure_probability_calibrated or {}
    mode_code, probability = _worst_mode(probabilities)
    threshold = PROBABILITY_THRESHOLDS.get(asset.asset_type, DEFAULT_PROBABILITY_THRESHOLD)
    if mode_code is None or probability < threshold:
        return False

    failure_mode = session.scalars(
        select(FailureMode).where(FailureMode.asset_type == asset.asset_type, FailureMode.code == mode_code)
    ).first()
    if failure_mode is None:
        log.info("no failure_mode row for %s/%s; not raising an order", asset.asset_type, mode_code)
        return False

    orders = WorkOrderRepository(session)
    if orders.open_for_mode(asset.id, failure_mode.id) is not None:
        return False

    explanation = ExplanationRepository(session).by_prediction(prediction.id)
    kb_entry = KnowledgeBaseRepository(session).for_failure_mode(failure_mode.id)

    WorkOrderService(session).create_order(
        None,
        WorkOrderCreate(
            asset_id=asset.id,
            component_id=prediction.component_id,
            type="predictive",
            priority=_priority(probability, failure_mode.severity),
            title=f"{failure_mode.name} predicted on {asset.code}",
            description=(
                f"Calibrated probability {probability:.0%} for failure mode '{mode_code}'."
                + (f" {kb_entry.likely_cause}" if kb_entry else "")
            ),
            failure_mode_id=failure_mode.id,
            prediction_id=prediction.id,
            explanation_id=explanation.id if explanation else None,
            est_duration_min=kb_entry.est_duration_min if kb_entry else None,
            parts=[{"code": part} for part in (kb_entry.parts if kb_entry else [])],
            created_via="auto",
        ),
    )
    return True


@celery_app.task(name="app.workers.tasks.maintenance.score_closed_orders", ignore_result=True)
def score_closed_orders(lookback_hours: int = 24) -> int:
    """Set prediction_was_correct on recently closed predictive orders (FR-MS-05).

    A prediction counts as correct when the technician's outcome does not say the machine was fine;
    the operator's own words are the ground truth here, not another model's output.
    """
    from sqlalchemy import select

    from app.core.db import get_sessionmaker
    from app.modules.maintenance.models import WorkOrder

    scored = 0
    since = datetime.now(UTC) - timedelta(hours=lookback_hours)
    with get_sessionmaker()() as session:
        orders = list(
            session.scalars(
                select(WorkOrder).where(
                    WorkOrder.status == "closed",
                    WorkOrder.type == "predictive",
                    WorkOrder.prediction_was_correct.is_(None),
                    WorkOrder.actual_end >= since,
                )
            )
        )
        for order in orders:
            order.prediction_was_correct = _outcome_confirms(order.outcome or "")
            scored += 1
        if scored:
            session.commit()
    return scored


def _worst_mode(probabilities: dict[str, float]) -> tuple[str | None, float]:
    candidates = {mode: p for mode, p in probabilities.items() if mode != "normal"}
    if not candidates:
        return None, 0.0
    mode = max(candidates, key=lambda m: candidates[m])
    return mode, float(candidates[mode])


def _priority(probability: float, severity: int) -> int:
    """1 is most urgent. A near-certain, high-severity mode lands at 1; a marginal, mild one at 4."""
    score = probability * severity  # severity is 1..4, probability 0..1
    if score >= 3.0:
        return 1
    if score >= 2.0:
        return 2
    return 3 if score >= 1.0 else 4


def _outcome_confirms(outcome: str) -> bool:
    negative = ("no fault", "no issue", "nothing found", "false alarm", "healthy", "no problem")
    return not any(phrase in outcome.lower() for phrase in negative)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
