"""Local attribution (FR-XAI-01, FR-XAI-03).

Every backend produces the same `ExplanationResult`, so the API, the narration templates and the
audit all read one shape regardless of whether the model was a tree, a sequence net, or a black box.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

import numpy as np

from twinvoice_xai.labels import FeatureLabels, load_labels


class Predictor(Protocol):
    def predict(self, X: Any) -> Any: ...


@dataclass(frozen=True)
class Attribution:
    feature: str
    label: str
    value: float
    unit: str
    contribution: float
    direction: str
    share: float
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExplanationResult:
    method: str
    base_value: float
    attributions: list[Attribution]
    temporal_attribution: dict[str, list[list[float]]] = field(default_factory=dict)
    compute_ms: int = 0

    def top(self, k: int) -> list[Attribution]:
        return self.attributions[:k]

    def top_features(self, k: int) -> list[str]:
        return [a.feature for a in self.attributions[:k]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "base_value": self.base_value,
            "attributions": [a.to_dict() for a in self.attributions],
            "temporal_attribution": self.temporal_attribution or None,
            "compute_ms": self.compute_ms,
        }


def build_attributions(
    feature_names: list[str],
    values: np.ndarray,
    contributions: np.ndarray,
    labels: FeatureLabels | None = None,
) -> list[Attribution]:
    """Rank by absolute contribution and attach human labels. `share` is of total absolute weight."""
    labels = labels or load_labels()
    values = np.asarray(values, dtype=float).reshape(-1)
    contributions = np.asarray(contributions, dtype=float).reshape(-1)
    if not (len(feature_names) == len(values) == len(contributions)):
        raise ValueError(
            f"length mismatch: {len(feature_names)} names, {len(values)} values, {len(contributions)} contributions"
        )

    total = float(np.abs(contributions).sum())
    order = np.argsort(-np.abs(contributions))
    out: list[Attribution] = []
    for rank, idx in enumerate(order, start=1):
        label = labels.get(feature_names[idx])
        contribution = float(contributions[idx])
        out.append(
            Attribution(
                feature=feature_names[idx],
                label=label.label,
                value=float(values[idx]),
                unit=label.unit,
                contribution=contribution,
                direction=label.direction_word(contribution),
                # total == 0 means a perfectly flat explanation; every share is 0, not a division by zero.
                share=abs(contribution) / total if total > 0 else 0.0,
                rank=rank,
            )
        )
    return out


def explain_tree(
    model: Any,
    x: np.ndarray,
    feature_names: list[str],
    *,
    labels: FeatureLabels | None = None,
    class_index: int | None = None,
) -> ExplanationResult:
    """Exact TreeSHAP for LightGBM / sklearn tree ensembles. The fast path: no sampling, no background set."""
    import shap

    started = time.perf_counter()
    x = np.asarray(x, dtype=float).reshape(1, -1)
    explainer = shap.TreeExplainer(model)
    raw = explainer.shap_values(x)
    values, base = _select_output(raw, explainer.expected_value, class_index)
    return ExplanationResult(
        method="tree_shap",
        base_value=base,
        attributions=build_attributions(feature_names, x[0], values, labels),
        compute_ms=int((time.perf_counter() - started) * 1000),
    )


def explain_kernel(
    predict: Any,
    x: np.ndarray,
    background: np.ndarray,
    feature_names: list[str],
    *,
    labels: FeatureLabels | None = None,
    nsamples: int = 200,
) -> ExplanationResult:
    """Model-agnostic fallback. Slow (nsamples forward passes), so only used when TreeSHAP cannot apply."""
    import shap

    started = time.perf_counter()
    x = np.asarray(x, dtype=float).reshape(1, -1)
    explainer = shap.KernelExplainer(predict, shap.sample(np.asarray(background, dtype=float), 50))
    raw = explainer.shap_values(x, nsamples=nsamples, silent=True)
    values, base = _select_output(raw, explainer.expected_value, None)
    return ExplanationResult(
        method="kernel_shap",
        base_value=base,
        attributions=build_attributions(feature_names, x[0], values, labels),
        compute_ms=int((time.perf_counter() - started) * 1000),
    )


def integrated_gradients(
    predict: Any,
    x: np.ndarray,
    baseline: np.ndarray,
    feature_names: list[str],
    *,
    labels: FeatureLabels | None = None,
    steps: int = 50,
) -> ExplanationResult:
    """Integrated gradients with a numeric gradient, for sequence models exposed only as a callable.

    Gradients are approximated by central differences because the model is a plain callable here;
    a framework-native autograd path would be faster but would tie this library to that framework.
    """
    started = time.perf_counter()
    x = np.asarray(x, dtype=float).reshape(-1)
    baseline = np.asarray(baseline, dtype=float).reshape(-1)
    diff = x - baseline
    eps = 1e-4
    grads = np.zeros_like(x)
    for step in range(steps):
        point = baseline + (step + 0.5) / steps * diff
        for j in range(len(x)):
            up, down = point.copy(), point.copy()
            up[j] += eps
            down[j] -= eps
            grads[j] += (float(predict(up.reshape(1, -1))) - float(predict(down.reshape(1, -1)))) / (2 * eps)
    contributions = diff * grads / steps
    return ExplanationResult(
        method="integrated_gradients",
        base_value=float(predict(baseline.reshape(1, -1))),
        attributions=build_attributions(feature_names, x, contributions, labels),
        compute_ms=int((time.perf_counter() - started) * 1000),
    )


def temporal_attribution(
    window: np.ndarray,
    contributions: np.ndarray,
    feature_names: list[str],
    timestamps: list[float],
) -> dict[str, list[list[float]]]:
    """Per-timestep weight for each feature (FR-XAI-03).

    `contributions` is (timesteps, features); the weight at each step is its share of that
    feature's absolute attribution across the window, so each series sums to 1.
    """
    contributions = np.asarray(contributions, dtype=float)
    if contributions.ndim != 2:
        raise ValueError("contributions must be (timesteps, features)")
    totals = np.abs(contributions).sum(axis=0)
    out: dict[str, list[list[float]]] = {}
    for j, name in enumerate(feature_names):
        if totals[j] == 0:
            continue
        weights = np.abs(contributions[:, j]) / totals[j]
        out[name] = [[float(t), float(w)] for t, w in zip(timestamps, weights, strict=False)]
    return out


def concept_segments(series: np.ndarray, *, spike_sigma: float = 3.0, shift_ratio: float = 0.5) -> str:
    """Classify a window's shape as trend | spike | level_shift | steady (FR-XAI-03 concept aggregation)."""
    series = np.asarray(series, dtype=float).reshape(-1)
    if len(series) < 4:
        return "steady"
    std = float(series.std())
    if std == 0:
        return "steady"

    # Spikes are measured against the median absolute deviation, not the standard deviation: a
    # single large outlier inflates its own threshold enough to hide itself from an SD test.
    median = float(np.median(series))
    deviations = np.abs(series - median)
    robust_sigma = 1.4826 * float(np.median(deviations))
    max_deviation = float(deviations.max())
    if robust_sigma == 0:
        return "spike" if max_deviation > 0 else "steady"
    if max_deviation > spike_sigma * robust_sigma:
        return "spike"

    half = len(series) // 2
    first, second = series[:half], series[half:]
    if abs(float(second.mean()) - float(first.mean())) > shift_ratio * std:
        # A monotone move across the window reads as a trend; an abrupt step reads as a level shift.
        steps = np.diff(series)
        return "trend" if float(np.sign(steps).sum()) / len(steps) > 0.6 else "level_shift"
    return "steady"


def _select_output(raw: Any, expected: Any, class_index: int | None) -> tuple[np.ndarray, float]:
    """Flatten SHAP's shape zoo (regression / binary / multiclass, list or ndarray) to (values, base)."""
    if isinstance(raw, list):
        idx = class_index if class_index is not None else int(np.argmax([np.abs(r).sum() for r in raw]))
        values = np.asarray(raw[idx], dtype=float).reshape(-1)
        base = expected[idx] if isinstance(expected, list | np.ndarray) else expected
        return values, float(base)

    values = np.asarray(raw, dtype=float)
    if values.ndim == 3:  # (samples, features, classes)
        idx = class_index if class_index is not None else int(np.argmax(np.abs(values[0]).sum(axis=0)))
        base = expected[idx] if isinstance(expected, list | np.ndarray) else expected
        return values[0, :, idx], float(base)
    base = expected[0] if isinstance(expected, list | np.ndarray) else expected
    return values.reshape(-1), float(base)
