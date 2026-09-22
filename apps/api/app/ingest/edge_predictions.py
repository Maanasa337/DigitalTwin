"""Edge predictions (FR-EDGE-02): `twinvoice/pred/{asset}` JSON -> predictions + explanations rows.

The edge runner has already inferred and explained; the platform only has to store, sync and fan out,
exactly as the server-side inference worker does, so the UI cannot tell the two apart except by
`source = 'edge'`.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from twinvoice_contracts.prediction import EdgePrediction
from twinvoice_xai.reason_card import build_reason_card

from app.modules.pdm.models import Model, Prediction
from app.modules.pdm.repository import ModelRepository
from app.modules.xai.models import Explanation
from app.modules.xai.modes import signature_mode
from app.modules.xai.service import to_attributions

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredEdgePrediction:
    prediction_id: uuid.UUID
    asset_code: str
    live_payload: dict[str, Any]
    ditto_properties: dict[str, Any]


def resolve_model(session: Session, model_version: str) -> Model | None:
    """`name:version` names one registered model; a bare `name` means its production model."""
    name, _, version = model_version.partition(":")
    repo = ModelRepository(session)
    if version:
        return repo.get_by_name_version(name, version)
    return repo.production_model(name)


def _reason_card(
    session: Session, asset_id: uuid.UUID, attributions: list[dict[str, Any]], health_index: float | None
) -> dict[str, Any] | None:
    """The same card the server's explain worker writes, so edge and server explanations read alike."""
    rehydrated = to_attributions(attributions)
    card = build_reason_card(signature_mode(session, asset_id, rehydrated, health_index), rehydrated)
    return card.to_dict() if card else None


def store_edge_prediction(
    session: Session, message: EdgePrediction, asset_id: uuid.UUID
) -> StoredEdgePrediction | None:
    """Write the prediction (and its explanation) in one transaction; None when it cannot be stored.

    Idempotent on the edge's own prediction id: store-and-forward replays after a reconnect, and
    QoS 1 may deliver twice, so a repeat is acknowledged without a second row.
    """
    model = resolve_model(session, message.model_version)
    if model is None:
        log.warning("edge prediction for %s names unknown model %s", message.asset_code, message.model_version)
        return None

    prediction_id = uuid.UUID(message.id)
    exists = session.scalar(
        select(Prediction.id).where(Prediction.id == prediction_id, Prediction.time == message.time)
    )
    if exists is not None:
        return None

    latency = message.latency_ms.infer_ms + (message.latency_ms.explain_ms or 0.0)
    rul = message.rul
    prediction = Prediction(
        id=prediction_id,
        time=message.time,
        asset_id=asset_id,
        model_id=model.id,
        window_start=message.window_start,
        window_end=message.window_end,
        health_index=round(message.health_index, 2) if message.health_index is not None else None,
        anomaly_score=message.anomaly_score,
        # The edge applies the bundle's isotonic map before publishing, so what it sends is calibrated.
        failure_probability_calibrated=message.failure_probability,
        rul_point=rul.point if rul else None,
        rul_low=rul.low if rul else None,
        rul_high=rul.high if rul else None,
        rul_unit=rul.unit if rul else None,
        rul_coverage=rul.coverage if rul else None,
        confidence_label=message.confidence.label,
        confidence_reasons=list(message.confidence.reasons),
        drift_flag=message.drift.flag,
        drift_score=message.drift.score,
        source="edge",
        latency_ms=round(latency),
    )
    session.add(prediction)
    session.flush()

    if message.explanation is not None and message.explanation.attributions:
        attributions = [a.model_dump() for a in message.explanation.attributions]
        session.add(
            Explanation(
                prediction_id=prediction_id,
                method="tree_shap",
                base_value=message.explanation.base_value,
                attributions=attributions,
                reason_card=_reason_card(session, asset_id, attributions, message.health_index),
                compute_ms=round(message.latency_ms.explain_ms) if message.latency_ms.explain_ms is not None else None,
            )
        )
    session.commit()

    properties = {
        "health_index": message.health_index,
        "rul_point": rul.point if rul else None,
        "rul_low": rul.low if rul else None,
        "rul_high": rul.high if rul else None,
        "rul_unit": rul.unit if rul else None,
        "confidence": message.confidence.label,
        "source": "edge",
        "time": message.time.isoformat(),
    }
    live = {"asset": message.asset_code, **{k: v for k, v in properties.items() if k != "rul_unit"}}
    return StoredEdgePrediction(prediction_id, message.asset_code, live, properties)
