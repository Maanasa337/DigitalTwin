"""Explanation quality metrics (FR-XAI-08).

Implemented directly on numpy rather than pulling in Quantus: these six metrics are each a handful
of lines, and keeping them here means the definitions used in the paper are the ones in the code.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from typing import Any

import numpy as np


def deletion_auc(
    predict: Callable[[np.ndarray], float], x: np.ndarray, contributions: np.ndarray, *, steps: int = 10
) -> float:
    """Remove features most-important-first; a faithful explanation makes the output fall fast.

    Normalised so 0 means the output collapses immediately (ideal) and 1 means removal changes nothing.
    """
    curve = _ablation_curve(predict, x, contributions, steps=steps, descending=True)
    return _normalised_auc(curve)


def insertion_auc(
    predict: Callable[[np.ndarray], float], x: np.ndarray, contributions: np.ndarray, *, steps: int = 10
) -> float:
    """Add features back most-important-first; a faithful explanation recovers the output fast. Higher is better."""
    x = np.asarray(x, dtype=float).reshape(-1)
    order = np.argsort(-np.abs(np.asarray(contributions, dtype=float).reshape(-1)))
    baseline = np.zeros_like(x)
    chunk = max(1, len(x) // steps)
    curve = [float(predict(baseline.reshape(1, -1)))]
    probe = baseline.copy()
    for start in range(0, len(order), chunk):
        probe[order[start : start + chunk]] = x[order[start : start + chunk]]
        curve.append(float(predict(probe.reshape(1, -1))))
    return _normalised_auc(curve)


def pgi(
    predict: Callable[[np.ndarray], float],
    x: np.ndarray,
    contributions: np.ndarray,
    *,
    top_k: int = 3,
    noise_scale: float = 0.1,
    trials: int = 20,
    seed: int = 0,
) -> float:
    """Prediction Gap on Important features: perturbing the top-k should move the output a lot."""
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float).reshape(-1)
    order = np.argsort(-np.abs(np.asarray(contributions, dtype=float).reshape(-1)))[:top_k]
    base = float(predict(x.reshape(1, -1)))
    scale = noise_scale * (np.abs(x[order]) + 1e-6)
    gaps = []
    for _ in range(trials):
        probe = x.copy()
        probe[order] += rng.normal(0.0, scale)
        gaps.append(abs(float(predict(probe.reshape(1, -1))) - base))
    return float(np.mean(gaps))


def sensitivity_max(
    explain: Callable[[np.ndarray], np.ndarray],
    x: np.ndarray,
    *,
    radius: float = 0.05,
    trials: int = 10,
    seed: int = 0,
) -> float:
    """Worst-case change in the attribution vector under a small input perturbation. Lower is better."""
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float).reshape(-1)
    reference = np.asarray(explain(x), dtype=float).reshape(-1)
    worst = 0.0
    for _ in range(trials):
        probe = x + rng.uniform(-radius, radius, size=x.shape) * (np.abs(x) + 1e-6)
        candidate = np.asarray(explain(probe), dtype=float).reshape(-1)
        worst = max(worst, float(np.linalg.norm(candidate - reference)))
    return worst


def sparsity(contributions: np.ndarray, *, threshold: float = 0.01) -> float:
    """Fraction of features carrying essentially no attribution. Higher means a more readable explanation."""
    values = np.abs(np.asarray(contributions, dtype=float).reshape(-1))
    total = values.sum()
    if total == 0:
        return 1.0
    return float((values / total < threshold).mean())


def truth_top1_agreement(contributions_per_sample: np.ndarray, drivers: list[int]) -> float:
    """On synthetic data the true driver is known: how often is it ranked first (FR-XAI-08)."""
    contributions_per_sample = np.abs(np.asarray(contributions_per_sample, dtype=float))
    if len(contributions_per_sample) != len(drivers):
        raise ValueError("one driver index is required per sample")
    top1 = contributions_per_sample.argmax(axis=1)
    return float(np.mean(top1 == np.asarray(drivers)))


def window_jaccard(top_features_per_window: list[list[str]], *, k: int = 3) -> float:
    """Stability: mean top-k overlap between consecutive windows of the same asset."""
    if len(top_features_per_window) < 2:
        return 1.0
    scores = []
    for previous, current in itertools.pairwise(top_features_per_window):
        a, b = set(previous[:k]), set(current[:k])
        union = a | b
        scores.append(len(a & b) / len(union) if union else 1.0)
    return float(np.mean(scores))


def _ablation_curve(
    predict: Callable[[np.ndarray], float],
    x: np.ndarray,
    contributions: np.ndarray,
    *,
    steps: int,
    descending: bool,
) -> list[float]:
    x = np.asarray(x, dtype=float).reshape(-1)
    magnitudes = np.abs(np.asarray(contributions, dtype=float).reshape(-1))
    order = np.argsort(-magnitudes if descending else magnitudes)
    chunk = max(1, len(x) // steps)
    probe = x.copy()
    curve = [float(predict(probe.reshape(1, -1)))]
    for start in range(0, len(order), chunk):
        probe[order[start : start + chunk]] = 0.0
        curve.append(float(predict(probe.reshape(1, -1))))
    return curve


def _normalised_auc(curve: list[float]) -> float:
    """Area under a curve rescaled to its own [min, max], so models on different scales compare."""
    values = np.asarray(curve, dtype=float)
    span = float(values.max() - values.min())
    if span == 0:
        return 0.0
    return float(np.trapezoid((values - values.min()) / span) / (len(values) - 1))


def as_metric_rows(
    model_id: str, method: str, metrics: dict[str, float], dataset_ref: str | None
) -> list[dict[str, Any]]:
    """Shape the metrics for explanation_quality_metrics rows."""
    return [
        {"model_id": model_id, "method": method, "metric": name, "value": float(value), "dataset_ref": dataset_ref}
        for name, value in metrics.items()
    ]
