"""Drift and out-of-distribution detection (FR-XAI-12).

Drift means the inputs moved; OOD means they moved somewhere the model has never been. Both feed the
confidence assessment and raise the UI banner, but they are different failures and stay separate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class DriftResult:
    flag: bool
    score: float
    drifted_features: list[str] = field(default_factory=list)
    ood_score: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ks_statistic(reference: np.ndarray, current: np.ndarray) -> float:
    """Two-sample Kolmogorov-Smirnov statistic: the largest gap between the two empirical CDFs."""
    reference = np.sort(np.asarray(reference, dtype=float).reshape(-1))
    current = np.sort(np.asarray(current, dtype=float).reshape(-1))
    if len(reference) == 0 or len(current) == 0:
        return 0.0
    grid = np.concatenate([reference, current])
    cdf_ref = np.searchsorted(reference, grid, side="right") / len(reference)
    cdf_cur = np.searchsorted(current, grid, side="right") / len(current)
    return float(np.abs(cdf_ref - cdf_cur).max())


def ks_critical(n_ref: int, n_cur: int, alpha: float = 0.05) -> float:
    """Critical value for the KS statistic at `alpha` (the standard large-sample approximation)."""
    coefficients = {0.10: 1.22, 0.05: 1.36, 0.01: 1.63}
    c = coefficients.get(round(alpha, 2), 1.36)
    if n_ref == 0 or n_cur == 0:
        return 1.0
    return c * np.sqrt((n_ref + n_cur) / (n_ref * n_cur))


def adwin_change_point(series: np.ndarray, *, delta: float = 0.002, min_window: int = 10) -> int | None:
    """ADWIN-style split search: the earliest index whose two sides differ beyond the Hoeffding bound.

    A simplified batch form of ADWIN — it examines a whole window at once rather than maintaining
    buckets incrementally, which is all the nightly drift job needs.
    """
    series = np.asarray(series, dtype=float).reshape(-1)
    n = len(series)
    if n < 2 * min_window:
        return None
    variance = float(series.var()) or 1e-12
    for cut in range(min_window, n - min_window + 1):
        left, right = series[:cut], series[cut:]
        harmonic = 1.0 / (1.0 / len(left) + 1.0 / len(right))
        bound = np.sqrt(2.0 / harmonic * variance * np.log(2.0 / delta)) + 2.0 / (3.0 * harmonic) * np.log(2.0 / delta)
        if abs(float(left.mean()) - float(right.mean())) > bound:
            return cut
    return None


def mahalanobis_ood(x: np.ndarray, mean: np.ndarray, covariance: np.ndarray) -> float:
    """Distance from the training manifold's centre, in standard deviations along each direction."""
    x = np.asarray(x, dtype=float).reshape(-1)
    mean = np.asarray(mean, dtype=float).reshape(-1)
    delta = x - mean
    # Pseudo-inverse: with more features than training windows the covariance is singular.
    inverse = np.linalg.pinv(np.asarray(covariance, dtype=float))
    return float(np.sqrt(max(0.0, delta @ inverse @ delta)))


def detect(
    reference: np.ndarray,
    current: np.ndarray,
    feature_names: list[str],
    *,
    alpha: float = 0.05,
    x: np.ndarray | None = None,
) -> DriftResult:
    """Per-feature KS test plus a Mahalanobis OOD score for the current point."""
    reference = np.asarray(reference, dtype=float)
    current = np.asarray(current, dtype=float)
    if reference.ndim != 2 or current.ndim != 2:
        raise ValueError("reference and current must be 2-D (samples, features)")

    statistics: dict[str, float] = {}
    drifted: list[str] = []
    critical = ks_critical(len(reference), len(current), alpha)
    for j, name in enumerate(feature_names):
        stat = ks_statistic(reference[:, j], current[:, j])
        statistics[name] = round(stat, 4)
        if stat > critical:
            drifted.append(name)

    ood = None
    if x is not None and len(reference) > 1:
        ood = round(mahalanobis_ood(x, reference.mean(axis=0), np.cov(reference, rowvar=False)), 4)

    score = max(statistics.values()) if statistics else 0.0
    return DriftResult(
        flag=bool(drifted),
        score=round(score, 4),
        drifted_features=drifted,
        ood_score=ood,
        details={"ks": statistics, "ks_critical": round(critical, 4)},
    )
