"""Anomaly detection: IsolationForest wrapper + health index computation."""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest


def normalise_anomaly(raw: np.ndarray, baseline_q95: float) -> np.ndarray:
    """Map IsolationForest ``-score_samples`` (0..1] to an anomaly score in [0, 1].

    Anything inside the healthy baseline's 95th percentile scores 0; the score then rises
    linearly to 1 at the IsolationForest maximum. Dividing by q95 instead would put healthy
    points at 0.8-1.0 and read a healthy machine as health ~0.
    """
    span = max(1.0 - baseline_q95, 1e-6)
    return np.clip((np.asarray(raw, dtype=np.float64) - baseline_q95) / span, 0.0, 1.0)


class AnomalyDetector:
    """IsolationForest wrapper fitted on healthy baseline data.

    After fitting, ``score(X)`` returns anomaly scores in [0, 1] where
    higher = more anomalous, and ``health_index(X)`` returns 0-100.
    """

    def __init__(
        self,
        contamination: float = 0.05,
        n_estimators: int = 200,
        random_state: int = 42,
    ) -> None:
        self.model = IsolationForest(
            contamination=contamination,
            n_estimators=n_estimators,
            random_state=random_state,
        )
        self._baseline_q95: float = 1.0

    def fit(self, X: np.ndarray) -> AnomalyDetector:
        """Fit on healthy (baseline) data."""
        self.model.fit(X)
        raw_scores = -self.model.score_samples(X)
        self._baseline_q95 = float(np.quantile(raw_scores, 0.95))
        if self._baseline_q95 < 1e-10:
            self._baseline_q95 = 1.0
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        """Normalised anomaly score in [0, 1]."""
        return normalise_anomaly(-self.model.score_samples(X), self._baseline_q95)

    def health_index(self, X: np.ndarray) -> np.ndarray:
        """Health index in [0, 100] — higher is healthier."""
        return 100.0 * (1.0 - self.score(X))

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Binary anomaly labels: 1 = normal, -1 = anomaly."""
        return self.model.predict(X)
