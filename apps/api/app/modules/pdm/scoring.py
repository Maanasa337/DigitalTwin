"""Server-side scoring with a trained model bundle (M5).

The 30 s inference job scores with this module and the explain worker rebuilds its feature vector
through it, so an explanation always describes the vector that was actually scored.

It mirrors the edge runner (`apps/edge/edge/onnx_infer.py`) output for output (conformal interval,
isotonic calibration, IsolationForest health index, interval-width confidence) but runs the native
estimator from ``model.pkl``, which only trusted server code may unpickle.

Feature windows are rebuilt from raw telemetry resampled to ``SAMPLE_PERIOD_S`` buckets: the synthetic
models were trained on the simulator export at that period, so ``window_size`` buckets span the same
stretch of machine time the model learned from, and per-sample statistics such as ``slope`` keep their
training scale. A trained metric the platform does not store as a sensor (or that stayed silent for
the whole window) is imputed with the training median of that feature and reported as a reason, so
confidence says so rather than the model silently reading zeros.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.modules.pdm.models import Model

log = logging.getLogger(__name__)

SAMPLE_PERIOD_S = 10  # the simulator export period the synthetic models were trained on
MIN_WINDOW_FILL = 0.5  # fewer populated buckets than this and the window is not scored
IMPUTED_SHARE_DOWNGRADE = 0.25  # above this share of imputed features, confidence drops a level
LIVE_TASKS = ("rul", "failure")
_LOWER = {"high": "medium", "medium": "low", "low": "low"}


@dataclass
class ScoringWindow:
    start: datetime
    end: datetime
    frame: pd.DataFrame  # one row per bucket, one column per trained sensor
    missing: list[str]  # trained sensors with no reading anywhere in the window
    fill: float  # share of buckets with at least one reading


@dataclass
class Score:
    health_index: float | None = None
    anomaly_score: float | None = None
    rul: dict[str, Any] | None = None
    failure_probability: dict[str, float] | None = None
    confidence: str | None = None
    reasons: list[str] = field(default_factory=list)


class LoadedModel:
    """A registered model's bundle plus its unpickled estimator, background rows and anomaly forest."""

    def __init__(self, model: Model) -> None:
        from twinvoice_pdm.registry.bundle import load_bundle, load_model_pickle

        directory = bundle_dir(model)
        self.model_id = model.id
        self.bundle = load_bundle(directory)
        self.meta = self.bundle.meta
        artifact = load_model_pickle(directory)
        self.estimator = artifact["model"]
        self.anomaly = artifact.get("anomaly")
        background = artifact.get("background")
        self.background = np.asarray(background, dtype=float) if background is not None else None
        self._medians = (
            np.median(self.background, axis=0)
            if self.background is not None and len(self.background)
            else np.zeros(len(self.feature_names))
        )

    @property
    def feature_names(self) -> list[str]:
        return self.bundle.feature_names

    @property
    def spec(self) -> Any:
        return self.bundle.spec

    @property
    def rul_unit(self) -> str:
        return str(self.meta.get("rul_unit") or "cycles")

    def median(self, index: int) -> float:
        return float(self._medians[index])


def bundle_dir(model: Model) -> Path:
    """Every bundle file lives next to model.pkl, which `artifact_uri` names."""
    return Path(model.artifact_uri.removeprefix("file://")).parent


_cache: dict[tuple[uuid.UUID, str], LoadedModel] = {}


def load(model: Model) -> LoadedModel | None:
    """The model ready to score, cached for the worker's lifetime; None when its bundle is not on disk."""
    key = (model.id, model.artifact_uri)
    if key in _cache:
        return _cache[key]
    directory = bundle_dir(model)
    if not (directory / "bundle.json").exists() or not (directory / "model.pkl").exists():
        log.warning("model %s v%s has no bundle at %s; run `make train`", model.name, model.version, directory)
        return None
    try:
        loaded = LoadedModel(model)
    except Exception:
        log.exception("could not load bundle for model %s v%s", model.name, model.version)
        return None
    _cache[key] = loaded
    return loaded


def select_model(session: Session, asset_id: uuid.UUID, asset_type: str) -> Model | None:
    """The production model that scores this asset: one bound to the asset, else its type's model.

    Plant-wide models without an asset type (C-MAPSS, AI4I) are benchmark models on public datasets;
    their features are not live metrics, so they never score the fleet.
    """
    candidates = session.scalars(
        select(Model)
        .where(
            Model.stage == "production",
            Model.task.in_(LIVE_TASKS),
            or_(Model.asset_id == asset_id, (Model.asset_id.is_(None)) & (Model.asset_type == asset_type)),
        )
        .order_by(Model.trained_at.desc())
    ).all()
    bound = [m for m in candidates if m.asset_id == asset_id]
    return next(iter(bound or candidates), None)


def telemetry_window(session: Session, asset_id: uuid.UUID, spec: Any, end: datetime) -> ScoringWindow | None:
    """The ``window_size`` buckets ending at ``end``, one column per trained sensor; None if too sparse."""
    period = timedelta(seconds=SAMPLE_PERIOD_S)
    start = end - spec.window_size * period
    rows = session.execute(
        text(
            """
            SELECT time_bucket(:period, t.time) AS bucket, s.metric_name, avg(t.value) AS value
            FROM telemetry t
            JOIN sensors s ON s.id = t.sensor_id
            WHERE s.asset_id = :asset_id AND s.deleted_at IS NULL
              AND s.metric_name = ANY(:metrics)
              AND t.time >= :start AND t.time < :end
            GROUP BY 1, 2
            """
        ),
        {"period": period, "asset_id": asset_id, "metrics": list(spec.sensor_cols), "start": start, "end": end},
    ).all()
    buckets = pd.date_range(start, periods=spec.window_size, freq=f"{SAMPLE_PERIOD_S}s")
    if rows:
        long = pd.DataFrame(rows, columns=["bucket", "metric", "value"])
        long["bucket"] = pd.to_datetime(long["bucket"], utc=True)
        wide = long.pivot_table(index="bucket", columns="metric", values="value", aggfunc="mean")
    else:
        wide = pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"))
    wide = wide.reindex(index=buckets, columns=list(spec.sensor_cols)).astype(float)
    fill = float(wide.notna().any(axis=1).mean())
    if fill < MIN_WINDOW_FILL:
        return None
    missing = [c for c in spec.sensor_cols if wide[c].isna().all()]
    # A reading carries forward until the next one, as on the edge; the leading gap takes the first.
    frame = wide.ffill().bfill().fillna(0.0)
    return ScoringWindow(start=start, end=end, frame=frame, missing=missing, fill=fill)


def feature_vector(loaded: LoadedModel, window: ScoringWindow) -> tuple[np.ndarray, list[str]]:
    """The window's features in the model's order, plus the names that had to be imputed."""
    from twinvoice_pdm.features import FeatureSpec, build_features

    base = loaded.spec
    frame = window.frame.reset_index(drop=True)
    spec = FeatureSpec(
        window_size=len(frame), stride=len(frame), stat_features=base.stat_features, sensor_cols=base.sensor_cols
    )
    features = build_features(frame, spec, group_col=None)
    row = features.iloc[-1] if not features.empty else pd.Series(dtype=float)
    missing = set(window.missing)
    values: list[float] = []
    imputed: list[str] = []
    for index, name in enumerate(loaded.feature_names):
        sensor = name.rsplit("_", 1)[0]
        value = row.get(name)
        if sensor in missing or value is None or not np.isfinite(value):
            values.append(loaded.median(index))
            imputed.append(name)
        else:
            values.append(float(value))
    return np.asarray(values, dtype=np.float64), imputed


def score(loaded: LoadedModel, x: np.ndarray) -> Score:
    """RUL with its conformal interval or calibrated failure probabilities, plus the health index."""
    from twinvoice_pdm.registry.bundle import apply_isotonic

    X = np.asarray(x, dtype=np.float64).reshape(1, -1)
    meta = loaded.meta
    out = Score()
    cap = float(meta.get("rul_cap") or np.inf)
    if meta["task"] == "rul":
        point = float(np.clip(loaded.estimator.predict(X)[0], 0, cap))
        q = float(meta.get("conformal_q") or 0.2 * point)
        out.rul = {
            "point": point,
            "low": float(np.clip(point - q, 0, cap)),
            "high": float(np.clip(point + q, 0, cap)),
            "unit": loaded.rul_unit,
            "coverage": meta.get("coverage"),
        }
        out.confidence, out.reasons = interval_confidence(2 * q, cap)
    else:
        probabilities = np.atleast_2d(loaded.estimator.predict_proba(X))
        if meta.get("isotonic"):
            probabilities = apply_isotonic(probabilities, meta["isotonic"])
        classes = meta.get("classes") or [str(i) for i in range(probabilities.shape[1])]
        out.failure_probability = {str(c): float(p) for c, p in zip(classes, probabilities[0], strict=True)}
        out.confidence = "medium"

    if loaded.anomaly is not None:
        out.anomaly_score = float(loaded.anomaly.score(X)[0])
        out.health_index = round(100.0 * (1.0 - out.anomaly_score), 2)
    elif out.rul is not None and np.isfinite(cap) and cap > 0:
        # No forest in the bundle: remaining life as a share of the modelled range stands in.
        out.health_index = round(100.0 * out.rul["point"] / cap, 2)
    return out


def interval_confidence(width: float, cap: float) -> tuple[str, list[str]]:
    """Interval width relative to the RUL range: a narrow interval is a confident one (as on the edge)."""
    if not np.isfinite(cap) or cap <= 0:
        return "medium", []
    relative = width / cap
    if relative < 0.15:
        return "high", []
    if relative < 0.35:
        return "medium", []
    return "low", ["wide_interval"]


def qualify(result: Score, window: ScoringWindow, imputed: list[str], n_features: int) -> None:
    """Fold the input's own weaknesses (gaps, imputed features) into the confidence and its reasons."""
    if window.fill < 0.9:
        result.reasons.append("partial_window")
    if imputed:
        result.reasons.append("imputed_features")
        if n_features and len(imputed) / n_features > IMPUTED_SHARE_DOWNGRADE and result.confidence:
            result.confidence = _LOWER[result.confidence]
