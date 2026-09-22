"""Celery beat task: periodic server-side inference with the trained production models (M5).

Every 30 s, each asset is scored by its production model (one bound to the asset, else the model for
its asset type) through `app.modules.pdm.scoring`: the feature window is rebuilt from raw telemetry,
the bundle's estimator gives RUL with its conformal interval (or calibrated failure probabilities),
and its IsolationForest gives the health index. The prediction is stored, explained off the hot
path, patched into Ditto and fanned out live.

Edge first: an asset the edge runner scored within ``EDGE_FRESH_S`` is skipped, so the edge and the
server never interleave two predictions for the same machine; if the edge goes quiet the server
takes the asset over on the next tick.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)

EDGE_FRESH_S = 120


@celery_app.task(name="app.workers.tasks.infer.infer_all_assets", ignore_result=True)
def infer_all_assets() -> None:
    """Score every active asset that has a production model and no fresh edge prediction."""
    from sqlalchemy import select

    from app.core.db import get_sessionmaker
    from app.modules.assets.models import Asset

    session_factory = get_sessionmaker()
    with session_factory() as session:
        assets = [
            (a.id, a.code, a.asset_type) for a in session.scalars(select(Asset).where(Asset.deleted_at.is_(None)))
        ]
    for asset_id, code, asset_type in assets:
        try:
            infer_asset(session_factory, asset_id, code, asset_type)
        except Exception:
            log.exception("inference failed for asset %s", code)


def _edge_is_fresh(session: Any, asset_id: uuid.UUID, now: datetime) -> bool:
    from sqlalchemy import select

    from app.modules.pdm.models import Prediction

    latest_edge = session.scalar(
        select(Prediction.time)
        .where(
            Prediction.asset_id == asset_id,
            Prediction.source == "edge",
            Prediction.time >= now - timedelta(seconds=EDGE_FRESH_S),
        )
        .limit(1)
    )
    return latest_edge is not None


def _window_end(now: datetime) -> datetime:
    """Snap to the bucket grid, so the explainer can rebuild exactly this window later."""
    from app.modules.pdm.scoring import SAMPLE_PERIOD_S

    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % SAMPLE_PERIOD_S, tz=UTC)


def infer_asset(session_factory: Any, asset_id: uuid.UUID, asset_code: str, asset_type: str) -> uuid.UUID | None:
    """Score one asset; returns the stored prediction's id, or None when it was skipped."""
    from app.modules.pdm import scoring
    from app.modules.pdm.models import Prediction

    started = time.monotonic()
    now = datetime.now(UTC)

    with session_factory() as session:
        if _edge_is_fresh(session, asset_id, now):
            return None
        model = scoring.select_model(session, asset_id, asset_type)
        if model is None:
            return None
        loaded = scoring.load(model)
        if loaded is None:
            return None
        window = scoring.telemetry_window(session, asset_id, loaded.spec, _window_end(now))
        if window is None:
            return None  # the asset has not reported enough of the window (stopped, or just started)

        x, imputed = scoring.feature_vector(loaded, window)
        result = scoring.score(loaded, x)
        scoring.qualify(result, window, imputed, len(loaded.feature_names))
        rul = result.rul or {}

        prediction = Prediction(
            time=now,
            asset_id=asset_id,
            model_id=model.id,
            window_start=window.start,
            window_end=window.end,
            health_index=result.health_index,
            anomaly_score=result.anomaly_score,
            failure_probability_calibrated=result.failure_probability,
            rul_point=rul.get("point"),
            rul_low=rul.get("low"),
            rul_high=rul.get("high"),
            rul_unit=rul.get("unit"),
            rul_coverage=round(rul["coverage"], 2) if rul.get("coverage") is not None else None,
            confidence_label=result.confidence,
            confidence_reasons=result.reasons,
            source="server",
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        session.add(prediction)
        session.commit()
        prediction_id = prediction.id

    # M6: explaining costs more than inferring, so it runs as its own task off this path.
    try:
        from app.workers.tasks.explain import explain_prediction

        explain_prediction.delay(str(prediction_id))
    except Exception:
        log.debug("could not enqueue explanation for prediction %s", prediction_id)

    properties = {
        "health_index": result.health_index,
        "rul_point": rul.get("point"),
        "rul_low": rul.get("low"),
        "rul_high": rul.get("high"),
        "rul_unit": rul.get("unit"),
        "confidence": result.confidence,
        "source": "server",
        "time": now.isoformat(),
    }
    _publish(asset_code, properties)
    return prediction_id


def _publish(asset_code: str, properties: dict[str, Any]) -> None:
    """Ditto's prediction feature and the live channel carry the same fields as edge predictions."""
    from app.core.config import get_settings
    from app.core.ditto import DittoClient

    settings = get_settings()
    try:
        ditto = DittoClient(settings.ditto_url, settings.ditto_subject)
        ditto.merge_thing(f"twinvoice:{asset_code}", {"features": {"prediction": {"properties": properties}}})
        ditto.close()
    except Exception:
        log.debug("ditto patch failed for prediction on %s", asset_code)

    try:
        import valkey

        v = valkey.from_url(settings.valkey_url)
        live = {"asset": asset_code, **{k: v for k, v in properties.items() if k != "rul_unit"}}
        v.publish(f"live:{asset_code}", json.dumps({"kind": "prediction", "payload": live}))
        v.close()
    except Exception:
        log.debug("valkey publish failed for prediction on %s", asset_code)
