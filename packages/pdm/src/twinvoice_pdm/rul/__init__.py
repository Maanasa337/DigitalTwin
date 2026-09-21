"""RUL estimation: LightGBM regression with MAPIE conformal prediction intervals."""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    import lightgbm as lgb
except ImportError:
    lgb = None  # type: ignore[assignment]

try:
    from mapie.regression import CrossConformalRegressor
except ImportError:
    CrossConformalRegressor = None  # type: ignore[assignment,misc]

# CV+ needs at least one point per fold to leave out; below this there is nothing to calibrate on.
MIN_CONFORMAL_SAMPLES = 10

RUL_CAP = 125  # Piecewise-linear target cap (C-MAPSS convention)


def cap_rul(rul: np.ndarray, cap: float = RUL_CAP) -> np.ndarray:
    """Apply piecewise-linear capping: values above `cap` are clipped."""
    return np.clip(rul, 0, cap)


class RulEstimator:
    """LightGBM regression for RUL with MAPIE conformal prediction intervals.

    Produces:
        - ``rul_point``: point estimate
        - ``rul_low``, ``rul_high``: 90% prediction interval (CV+)
    """

    def __init__(
        self,
        n_estimators: int = 500,
        max_depth: int = 6,
        learning_rate: float = 0.03,
        random_state: int = 42,
        coverage: float = 0.90,
    ) -> None:
        if lgb is None:
            raise ImportError("lightgbm is required for RulEstimator")
        self.base_model = lgb.LGBMRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_state=random_state,
            verbose=-1,
        )
        self.conformal: Any | None = None
        self.coverage = coverage
        self._fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray, conformal: bool = True) -> RulEstimator:
        """Fit the regressor. If conformal=True, wraps with MAPIE CV+ for intervals.

        CV+ rather than a split: an asset in cold start has only hours of history, and holding a
        calibration set back out of that would cost more accuracy than the interval is worth.
        """
        y_capped = cap_rul(y)

        # Always fit the base model on everything: CV+ keeps its calibration models to itself, and
        # SHAP and the importance chart need one fitted tree model to attribute.
        self.base_model.fit(X, y_capped)

        n_folds = min(5, len(y_capped))
        if conformal and CrossConformalRegressor is not None and len(y_capped) >= MIN_CONFORMAL_SAMPLES:
            self.conformal = CrossConformalRegressor(
                estimator=self.base_model,
                confidence_level=self.coverage,
                method="plus",
                cv=n_folds,
                random_state=42,
            )
            self.conformal.fit_conformalize(X, y_capped)
        else:
            self.conformal = None

        self._fitted = True
        return self

    def predict(self, X: np.ndarray) -> dict[str, np.ndarray]:
        """Return point estimate and prediction interval.

        Returns dict with keys: ``point``, ``low``, ``high``.
        """
        if self.conformal is not None:
            # MAPIE 1.x: the confidence level is set on the estimator, and predict_interval
            # returns (point, intervals) with intervals shaped (n, 2, n_confidence_levels).
            y_pred, y_pis = self.conformal.predict_interval(X)
            point = np.clip(y_pred, 0, RUL_CAP)
            low = np.clip(y_pis[:, 0, 0], 0, RUL_CAP)
            high = np.clip(y_pis[:, 1, 0], 0, RUL_CAP)
        else:
            point = np.clip(self.base_model.predict(X), 0, RUL_CAP)
            # Fallback: ±20% interval
            low = point * 0.8
            high = point * 1.2

        return {"point": point, "low": low, "high": high}

    @property
    def feature_importances_(self) -> np.ndarray:
        return self.base_model.feature_importances_
