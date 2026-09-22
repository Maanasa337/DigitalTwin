"""Celery task: explain one prediction (M6).

Enqueued by the inference worker right after a prediction is written. Runs off the hot path because
TreeSHAP plus a counterfactual search costs more than the inference itself, and the UI reads the
explanation lazily anyway.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)

TOP_K = 8


@celery_app.task(name="app.workers.tasks.explain.explain_prediction", ignore_result=True, max_retries=2)
def explain_prediction(prediction_id: str) -> None:
    """Compute and store the explanation for one prediction; idempotent on re-delivery."""
    from app.core.db import get_sessionmaker
    from app.modules.xai.repository import ExplanationRepository

    pid = uuid.UUID(prediction_id)
    with get_sessionmaker()() as session:
        repo = ExplanationRepository(session)
        # The unique index on prediction_id would reject a duplicate anyway; checking first keeps
        # a retried task from burning a SHAP computation to hit that error.
        if repo.by_prediction(pid) is not None:
            return
        try:
            _explain(session, pid)
        except Exception:
            log.exception("explanation failed for prediction %s", prediction_id)
            session.rollback()
            raise


def _explain(session: Any, prediction_id: uuid.UUID) -> None:
    import numpy as np
    from twinvoice_xai.glassbox import agreement
    from twinvoice_xai.reason_card import build_reason_card

    from app.modules.pdm.models import Model, Prediction
    from app.modules.xai.models import Counterfactual, Explanation

    prediction = session.get(Prediction, prediction_id)
    if prediction is None:
        log.warning("prediction %s vanished before it could be explained", prediction_id)
        return
    model = session.get(Model, prediction.model_id)
    if model is None:
        log.warning("model %s for prediction %s is gone", prediction.model_id, prediction_id)
        return

    feature_names, values = _feature_vector(session, prediction, model)
    if not feature_names:
        log.warning("no feature vector recoverable for prediction %s", prediction_id)
        return

    artifact = _load_artifact(model.artifact_uri)
    if artifact is None:
        # No artifact on disk (fresh environment, or an edge-trained model): a contribution-free
        # explanation would be misleading, so skip rather than store zeros.
        log.warning("model artifact %s unavailable; skipping explanation", model.artifact_uri)
        return

    result = _attribute(artifact, np.asarray(values), feature_names)
    ebm_result = _ebm_second_opinion(model, np.asarray(values), feature_names)

    failure_mode = _predicted_mode(session, prediction, result.attributions)
    card = build_reason_card(
        failure_mode,
        result.attributions,
        mode_probability=_mode_probability(prediction, failure_mode),
    )

    explanation = Explanation(
        prediction_id=prediction_id,
        method=result.method,
        base_value=result.base_value,
        attributions=[a.to_dict() for a in result.attributions[:TOP_K]],
        temporal_attribution=result.temporal_attribution or None,
        ebm_terms=ebm_result.to_dict() if ebm_result else None,
        agreement=agreement(result.top_features(3), ebm_result.top_features) if ebm_result else None,
        reason_card=card.to_dict() if card else None,
        compute_ms=result.compute_ms,
    )
    session.add(explanation)
    session.flush()

    counterfactual = _counterfactual(artifact, np.asarray(values), feature_names, prediction)
    if counterfactual is not None and counterfactual.found:
        session.add(
            Counterfactual(
                explanation_id=explanation.id,
                target=counterfactual.target,
                changes=[c.to_dict() for c in counterfactual.changes],
                outcome=counterfactual.outcome,
                feasibility_score=counterfactual.feasibility_score,
                action_text=counterfactual.action_text,
            )
        )
    session.commit()


def _feature_vector(session: Any, prediction: Any, model: Any) -> tuple[list[str], list[float]]:
    """Rebuild exactly the vector the inference job scored for this prediction.

    Server predictions store the bucket-aligned window they scored, so `scoring.telemetry_window`
    over the same span yields the same buckets and `scoring.feature_vector` the same features,
    imputations included. A model registered before bundles existed has nothing to rebuild from.
    """
    from app.modules.pdm import scoring

    loaded = scoring.load(model)
    if loaded is None:
        return [], []
    window = scoring.telemetry_window(session, prediction.asset_id, loaded.spec, prediction.window_end)
    if window is None:
        return [], []
    values, _ = scoring.feature_vector(loaded, window)
    return loaded.feature_names, [float(v) for v in values]


def _load_artifact(artifact_uri: str) -> Any | None:
    import pathlib
    import pickle

    path = pathlib.Path(artifact_uri.removeprefix("file://"))
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            return pickle.load(handle)
    except Exception:
        log.exception("could not load model artifact %s", artifact_uri)
        return None


def _estimator(artifact: Any) -> Any | None:
    """The fitted estimator inside a stored artifact, or None when the bundle has no model."""
    return artifact.get("model") if isinstance(artifact, dict) else artifact


def _attribute(artifact: Any, values: Any, feature_names: list[str]) -> Any:
    import numpy as np
    from twinvoice_xai.attribution import ExplanationResult, explain_kernel, explain_tree

    estimator = _estimator(artifact)
    if estimator is None:
        return ExplanationResult(method="none", base_value=0.0, attributions=[])
    try:
        return explain_tree(estimator, values, feature_names)
    except Exception:
        log.info("TreeSHAP not applicable; falling back to KernelSHAP", exc_info=True)

    background = artifact.get("background") if isinstance(artifact, dict) else None
    if background is None:
        # Without a background set KernelSHAP has nothing to marginalise over; a single-row
        # baseline of the point itself would return all-zero contributions, so report none.
        return ExplanationResult(method="kernel_shap", base_value=0.0, attributions=[])
    return explain_kernel(estimator.predict, values, np.asarray(background), feature_names)


def _ebm_second_opinion(model: Any, values: Any, feature_names: list[str]) -> Any | None:
    from twinvoice_xai.glassbox import explain_ebm

    ebm_uri = (model.hyperparams or {}).get("ebm_uri")
    if not ebm_uri:
        return None
    ebm = _load_artifact(ebm_uri)
    if ebm is None:
        return None
    try:
        return explain_ebm(ebm, values, feature_names)
    except Exception:
        log.exception("EBM second opinion failed for model %s", model.id)
        return None


def _predicted_mode(session: Any, prediction: Any, attributions: list[Any]) -> str:
    """The classifier's most probable mode; for a RUL-only model, the mode the evidence supports."""
    from app.modules.xai.modes import signature_mode

    probabilities = prediction.failure_probability_calibrated or prediction.failure_probability or {}
    if not probabilities:
        return signature_mode(session, prediction.asset_id, attributions, prediction.health_index)
    return max(probabilities, key=lambda mode: probabilities[mode])


def _mode_probability(prediction: Any, mode: str) -> float | None:
    probabilities = prediction.failure_probability_calibrated or prediction.failure_probability or {}
    value = probabilities.get(mode)
    return float(value) if value is not None else None


def _counterfactual(artifact: Any, values: Any, feature_names: list[str], prediction: Any) -> Any | None:
    """Ask what actionable change would push RUL back over the healthy threshold."""
    from twinvoice_xai.counterfactual import search_counterfactual

    if prediction.rul_point is None:
        return None
    estimator = _estimator(artifact)
    if estimator is None:
        return None
    target_rul = max(60.0, float(prediction.rul_point) * 1.5)

    try:
        return search_counterfactual(
            lambda row: float(estimator.predict(row)[0]),
            values,
            feature_names,
            target=f"rul>={target_rul:.0f}",
            satisfied=lambda value: value >= target_rul,
        )
    except Exception:
        log.exception("counterfactual search failed for prediction %s", prediction.id)
        return None
