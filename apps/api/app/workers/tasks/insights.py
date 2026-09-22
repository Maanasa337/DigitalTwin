"""Celery task: model insights (FR-XAI-02, FR-XAI-08).

For one model: global importance (mean |TreeSHAP| per feature), partial dependence of the top
features, and the explanation-quality metrics of `twinvoice_xai.quality` — deletion and insertion AUC,
prediction gap on important features, max sensitivity and sparsity — averaged over a sample of the
background rows saved in the model's bundle, plus window stability measured on the model's stored
live explanations.

Runs after every training run, hourly for the production models (window stability moves as live
explanations accumulate), and on demand from the explanation-quality page.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from typing import Any

import numpy as np

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)

QUALITY_SAMPLE = 20  # background rows each metric is averaged over
SENSITIVITY_TRIALS = 5
PDP_FEATURES = 3
STABILITY_WINDOWS = 500  # latest live explanations read for window stability
METHOD = "tree_shap"


@celery_app.task(name="app.workers.tasks.insights.compute_model_insights", ignore_result=True)
def compute_model_insights(model_id: str) -> None:
    from app.core.db import get_sessionmaker

    with get_sessionmaker()() as session:
        compute(session, uuid.UUID(model_id))


@celery_app.task(name="app.workers.tasks.insights.refresh_production_insights", ignore_result=True)
def refresh_production_insights() -> None:
    from sqlalchemy import select

    from app.core.db import get_sessionmaker
    from app.modules.pdm.models import Model

    with get_sessionmaker()() as session:
        ids = list(session.scalars(select(Model.id).where(Model.stage == "production")))
        for model_id in ids:
            try:
                compute(session, model_id)
            except Exception:
                log.exception("insights failed for model %s", model_id)
                session.rollback()


def compute(session: Any, model_id: uuid.UUID) -> bool:
    """Write the model's importance, partial dependence and quality metrics; False when it has no bundle."""
    import shap
    from sqlalchemy import delete
    from twinvoice_xai import quality
    from twinvoice_xai.glassbox import global_importance, partial_dependence

    from app.modules.pdm import scoring
    from app.modules.pdm.models import Model
    from app.modules.xai.models import ExplanationQualityMetric

    model = session.get(Model, model_id)
    if model is None:
        return False
    loaded = scoring.load(model)
    if loaded is None or loaded.background is None or len(loaded.background) < 2:
        log.warning("model %s v%s has no bundle background to compute insights on", model.name, model.version)
        return False

    names = loaded.feature_names
    X = loaded.background
    predict, contributions = _model_functions(loaded, shap.TreeExplainer(loaded.estimator))

    importance = global_importance(None, names, contributions(X))
    top = sorted(importance, key=lambda name: importance[name], reverse=True)[:PDP_FEATURES]
    pdp = {name: partial_dependence(predict, X, names.index(name)) for name in top}
    model.hyperparams = {**(model.hyperparams or {}), "global_importance": importance, "partial_dependence": pdp}

    sample = X[np.linspace(0, len(X) - 1, min(QUALITY_SAMPLE, len(X))).astype(int)]
    per_row: dict[str, list[float]] = defaultdict(list)
    for row in sample:
        c = contributions(row.reshape(1, -1))[0]
        scalar = _scalar(predict)
        per_row["deletion_auc"].append(quality.deletion_auc(scalar, row, c))
        per_row["insertion_auc"].append(quality.insertion_auc(scalar, row, c))
        per_row["pgi"].append(quality.pgi(scalar, row, c))
        per_row["sparsity"].append(quality.sparsity(c))
        per_row["sensitivity_max"].append(
            quality.sensitivity_max(lambda r: contributions(r.reshape(1, -1))[0], row, trials=SENSITIVITY_TRIALS)
        )
    sample_ref = f"{model.dataset_ref} · {len(sample)} background rows"
    rows = [
        ExplanationQualityMetric(
            model_id=model.id, method=METHOD, metric=name, value=float(np.mean(v)), dataset_ref=sample_ref
        )
        for name, v in per_row.items()
    ]

    stability = _window_stability(session, model.id)
    if stability is not None:
        value, windows = stability
        rows.append(
            ExplanationQualityMetric(
                model_id=model.id,
                method=METHOD,
                metric="window_jaccard",
                value=value,
                dataset_ref=f"live explanations · {windows} windows",
            )
        )

    # One current value per metric: the page reads the latest run, not a history.
    session.execute(delete(ExplanationQualityMetric).where(ExplanationQualityMetric.model_id == model.id))
    session.add_all(rows)
    session.commit()
    log.info("insights for %s v%s: %s", model.name, model.version, {r.metric: round(r.value, 4) for r in rows})
    return True


def _model_functions(loaded: Any, explainer: Any) -> tuple[Any, Any]:
    """`predict(X) -> (n,)` and `contributions(X) -> (n, features)` for the output the model reports."""
    estimator = loaded.estimator
    if loaded.meta["task"] == "rul":
        return estimator.predict, lambda A: np.asarray(explainer.shap_values(A), dtype=float).reshape(len(A), -1)

    classes = [str(c) for c in (loaded.meta.get("classes") or [])]
    positive = classes.index("failure") if "failure" in classes else 1

    def predict(A: np.ndarray) -> np.ndarray:
        return np.asarray(estimator.predict_proba(A))[:, positive]

    def contributions(A: np.ndarray) -> np.ndarray:
        raw = explainer.shap_values(A)
        if isinstance(raw, list):
            return np.asarray(raw[positive], dtype=float)
        values = np.asarray(raw, dtype=float)
        return values[:, :, positive] if values.ndim == 3 else values

    return predict, contributions


def _scalar(predict: Any) -> Any:
    return lambda A: float(np.asarray(predict(A)).reshape(-1)[0])


def _window_stability(session: Any, model_id: uuid.UUID) -> tuple[float, int] | None:
    """Mean top-3 Jaccard between consecutive live explanations of the same asset."""
    from sqlalchemy import select
    from twinvoice_xai.quality import window_jaccard

    from app.modules.pdm.models import Prediction
    from app.modules.xai.models import Explanation

    rows = session.execute(
        select(Prediction.asset_id, Explanation.attributions)
        .join(Explanation, Explanation.prediction_id == Prediction.id)
        .where(Prediction.model_id == model_id)
        .order_by(Prediction.time.desc())
        .limit(STABILITY_WINDOWS)
    ).all()
    by_asset: dict[uuid.UUID, list[list[str]]] = defaultdict(list)
    for asset_id, attributions in reversed(rows):
        ranked = sorted(attributions or [], key=lambda a: a.get("rank", 0))
        by_asset[asset_id].append([a["feature"] for a in ranked])
    scored = [(window_jaccard(tops), len(tops) - 1) for tops in by_asset.values() if len(tops) >= 2]
    pairs = sum(n for _, n in scored)
    if not pairs:
        return None
    return float(sum(value * n for value, n in scored) / pairs), len(rows)
