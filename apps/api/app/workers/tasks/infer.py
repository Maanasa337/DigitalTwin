"""Celery beat task: periodic inference for all assets with a production model.

Pulls the latest telemetry window, runs anomaly/failure/RUL inference,
writes a prediction row, patches Ditto, and publishes live updates.
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


@celery_app.task(name="app.workers.tasks.infer.infer_all_assets", ignore_result=True)
def infer_all_assets() -> None:
    """Iterate over all assets that have a production model and run inference."""
    from sqlalchemy import select

    from app.core.db import get_sessionmaker
    from app.modules.assets.models import Asset
    from app.modules.pdm.models import Model

    session_factory = get_sessionmaker()
    with session_factory() as session:
        # Find all assets with at least one production model
        production_models = list(session.scalars(select(Model).where(Model.stage == "production")))
        if not production_models:
            return

        assets = list(session.scalars(select(Asset).where(Asset.deleted_at.is_(None))))

        for asset in assets:
            try:
                _infer_single_asset(session_factory, asset.id, asset.code, production_models)
            except Exception:
                log.exception("inference failed for asset %s", asset.code)


def _infer_single_asset(
    session_factory: Any,
    asset_id: uuid.UUID,
    asset_code: str,
    production_models: list[Any],
) -> None:
    """Run inference pipeline for a single asset."""
    from sqlalchemy import text

    from app.core.config import get_settings
    from app.core.ditto import DittoClient
    from app.modules.pdm.models import Prediction

    settings = get_settings()
    start_time = time.monotonic()

    with session_factory() as session:
        # Pull latest telemetry window (last 10 minutes of 1-minute aggregates)
        now = datetime.now(UTC)
        window_end = now
        window_start = now - timedelta(minutes=10)

        rows = (
            session.execute(
                text("""
                SELECT sensor_id, bucket, avg, min, max, std, n
                FROM telemetry_1m
                WHERE sensor_id IN (
                    SELECT id FROM sensors WHERE asset_id = :asset_id AND deleted_at IS NULL
                )
                AND bucket >= :start AND bucket < :end
                ORDER BY bucket
            """),
                {"asset_id": asset_id, "start": window_start, "end": window_end},
            )
            .mappings()
            .all()
        )

        if len(rows) < 5:
            return  # Not enough data for inference

        # Use the first production model (simplified — in practice, match by asset_type)
        model = production_models[0]

        # Build simple feature vector from aggregated telemetry
        sensor_avgs: dict[uuid.UUID, list[float]] = {}
        for row in rows:
            sid = row["sensor_id"]
            sensor_avgs.setdefault(sid, []).append(row["avg"] or 0.0)

        # Compute basic stats per sensor
        features: dict[str, float] = {}
        for sid, values in sensor_avgs.items():
            if not values:
                continue
            mean_val = sum(values) / len(values)
            std_val = (sum((v - mean_val) ** 2 for v in values) / len(values)) ** 0.5
            features[f"{sid}_mean"] = mean_val
            features[f"{sid}_std"] = std_val

        if not features:
            return

        # Simple anomaly score (normalized distance from typical values)
        all_stds = [v for k, v in features.items() if k.endswith("_std")]
        anomaly_score = sum(all_stds) / len(all_stds) if all_stds else 0.0

        # Health index (inverse of anomaly)
        health_index = max(0.0, min(100.0, 100.0 * (1.0 - min(anomaly_score / 10.0, 1.0))))

        # Simple RUL estimation (placeholder — real model would use trained weights)
        rul_point = max(1.0, 100.0 - anomaly_score * 20.0)
        rul_low = max(1.0, rul_point * 0.7)
        rul_high = rul_point * 1.3

        # Confidence
        n_sensors = len(sensor_avgs)
        confidence_label = "high" if n_sensors >= 5 else ("medium" if n_sensors >= 3 else "low")
        confidence_reasons: list[str] = []
        if n_sensors < 5:
            confidence_reasons.append("few_sensors")

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        prediction = Prediction(
            time=now,
            asset_id=asset_id,
            model_id=model.id,
            window_start=window_start,
            window_end=window_end,
            health_index=round(health_index, 2),
            anomaly_score=anomaly_score,
            rul_point=rul_point,
            rul_low=rul_low,
            rul_high=rul_high,
            rul_unit="cycles",
            confidence_label=confidence_label,
            confidence_reasons=confidence_reasons,
            source="server",
            latency_ms=elapsed_ms,
        )
        session.add(prediction)
        session.commit()

        # M6: explaining costs more than inferring, so it runs as its own task off this path.
        try:
            from app.workers.tasks.explain import explain_prediction

            explain_prediction.delay(str(prediction.id))
        except Exception:
            log.debug("could not enqueue explanation for prediction %s", prediction.id)

        # Patch Ditto with prediction
        try:
            ditto = DittoClient(settings.ditto_url, settings.ditto_subject)
            ditto.merge_thing(
                f"twinvoice:{asset_code}",
                {
                    "features": {
                        "prediction": {
                            "properties": {
                                "health_index": float(health_index),
                                "rul_point": rul_point,
                                "rul_low": rul_low,
                                "rul_high": rul_high,
                                "rul_unit": "cycles",
                                "confidence": confidence_label,
                                "time": now.isoformat(),
                            }
                        }
                    }
                },
            )
            ditto.close()
        except Exception:
            log.debug("ditto patch failed for prediction on %s", asset_code)

        # Publish live update via Valkey
        try:
            import valkey

            v = valkey.from_url(settings.valkey_url)
            msg = json.dumps(
                {
                    "kind": "prediction",
                    "payload": {
                        "asset": asset_code,
                        "health_index": float(health_index),
                        "rul_point": rul_point,
                        "rul_low": rul_low,
                        "rul_high": rul_high,
                        "confidence": confidence_label,
                        "time": now.isoformat(),
                    },
                }
            )
            v.publish(f"live:{asset_code}", msg)
            v.close()
        except Exception:
            log.debug("valkey publish failed for prediction on %s", asset_code)
