"""Glass-box second opinion (FR-XAI-04).

An EBM is trained on the same features as the production model. Where the two disagree about which
features matter, the confidence assessment says so instead of presenting one story as settled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

DISAGREEMENT_THRESHOLD = 0.34


@dataclass(frozen=True)
class GlassboxResult:
    terms: dict[str, float]
    top_features: list[str]
    intercept: float

    def to_dict(self) -> dict[str, Any]:
        return {"terms": self.terms, "top_features": self.top_features, "intercept": self.intercept}


def fit_ebm(X: np.ndarray, y: np.ndarray, feature_names: list[str], *, task: str = "regression", **kwargs: Any) -> Any:
    """Train the parallel EBM. Imported lazily so the rest of this library loads without interpret."""
    if task == "classification":
        from interpret.glassbox import ExplainableBoostingClassifier as EBM
    else:
        from interpret.glassbox import ExplainableBoostingRegressor as EBM

    model = EBM(feature_names=feature_names, **kwargs)
    model.fit(np.asarray(X, dtype=float), np.asarray(y))
    return model


def explain_ebm(model: Any, x: np.ndarray, feature_names: list[str], *, top_k: int = 8) -> GlassboxResult:
    """Per-term contributions for one row. Only main effects are reported; pair terms are folded out."""
    x = np.asarray(x, dtype=float).reshape(1, -1)
    local = model.explain_local(x)
    data = local.data(0)
    names = list(data.get("names") or feature_names)
    scores = [float(s) for s in data.get("scores") or []]

    terms: dict[str, float] = {}
    for name, score in zip(names, scores, strict=False):
        if " x " in name or " & " in name:  # interaction term, not a single feature
            continue
        terms[name] = score

    ranked = sorted(terms, key=lambda n: abs(terms[n]), reverse=True)[:top_k]
    return GlassboxResult(terms=terms, top_features=ranked, intercept=float(getattr(model, "intercept_", [0.0])[0]))


def top3_jaccard(shap_top: list[str], ebm_top: list[str]) -> float:
    """Overlap between the two models' top-3 stories. Below 0.34 they are effectively telling different ones."""
    a, b = set(shap_top[:3]), set(ebm_top[:3])
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def agreement(shap_top: list[str], ebm_top: list[str]) -> dict[str, Any]:
    jaccard = top3_jaccard(shap_top, ebm_top)
    return {
        "shap_vs_ebm_top3_jaccard": round(jaccard, 4),
        "disagreement": jaccard < DISAGREEMENT_THRESHOLD,
        "shap_top3": shap_top[:3],
        "ebm_top3": ebm_top[:3],
    }


def global_importance(model: Any, feature_names: list[str], shap_values: np.ndarray | None = None) -> dict[str, float]:
    """Mean |SHAP| per feature over a sample, for the model-detail page (FR-XAI-02)."""
    if shap_values is None:
        raise ValueError("shap_values are required to compute global importance")
    values = np.abs(np.asarray(shap_values, dtype=float))
    if values.ndim == 3:
        values = values.mean(axis=2)
    means = values.mean(axis=0)
    return {name: float(m) for name, m in zip(feature_names, means, strict=False)}


def partial_dependence(
    predict: Any, X: np.ndarray, feature_index: int, *, grid_size: int = 20
) -> list[list[float]]:
    """PDP for one feature: average prediction as that feature sweeps its observed range."""
    X = np.asarray(X, dtype=float)
    column = X[:, feature_index]
    grid = np.linspace(float(column.min()), float(column.max()), grid_size)
    out: list[list[float]] = []
    for point in grid:
        probe = X.copy()
        probe[:, feature_index] = point
        out.append([float(point), float(np.mean(predict(probe)))])
    return out
