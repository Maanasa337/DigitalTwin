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
        cap: float = RUL_CAP,
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
        # 125 cycles is the C-MAPSS convention; the simulator's RUL is in hours and needs its own.
        self.cap = cap
        self._fitted = False

    def fit(
        self, X: np.ndarray, y: np.ndarray, conformal: bool = True, groups: np.ndarray | None = None
    ) -> RulEstimator:
        """Fit the regressor. If conformal=True, wraps with MAPIE CV+ for intervals.

        CV+ rather than a split: an asset in cold start has only hours of history, and holding a
        calibration set back out of that would cost more accuracy than the interval is worth.

        ``groups`` (e.g. the engine or asset each window came from) makes the CV+ folds leave whole
        groups out. Overlapping windows of one unit in both the fit and the calibration fold make the
        residuals look small, and the interval then under-covers on units it has never seen.
        """
        y_capped = cap_rul(y, self.cap)

        # Always fit the base model on everything: CV+ keeps its calibration models to itself, and
        # SHAP and the importance chart need one fitted tree model to attribute.
        self.base_model.fit(X, y_capped)

        if conformal and CrossConformalRegressor is not None and len(y_capped) >= MIN_CONFORMAL_SAMPLES:
            self.conformal = CrossConformalRegressor(
                estimator=self.base_model,
                confidence_level=self.coverage,
                method="plus",
                cv=_folds(len(y_capped), groups),
                random_state=42,
            )
            self.conformal.fit_conformalize(X, y_capped, groups=groups)
        else:
            self.conformal = None

        self._fitted = True
        return self

    def residual_quantile(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray | None = None) -> float:
        """The coverage-quantile of absolute out-of-fold residuals: a single conformal half-width.

        The edge runner cannot carry CV+'s fold models, so it serves ``point ± q`` instead — the
        jackknife interval, which has the same nominal coverage without per-point adaptivity.
        """
        from sklearn.base import clone
        from sklearn.model_selection import cross_val_predict

        y_capped = cap_rul(y, self.cap)
        if len(y_capped) < MIN_CONFORMAL_SAMPLES:
            return float(np.max(np.abs(y_capped - self.base_model.predict(X)))) if len(y_capped) else 0.0
        oof = cross_val_predict(clone(self.base_model), X, y_capped, cv=_folds(len(y_capped), groups), groups=groups)
        return float(np.quantile(np.abs(y_capped - oof), self.coverage))

    def predict(self, X: np.ndarray) -> dict[str, np.ndarray]:
        """Return point estimate and prediction interval.

        Returns dict with keys: ``point``, ``low``, ``high``.
        """
        if self.conformal is not None:
            # MAPIE 1.x: the confidence level is set on the estimator, and predict_interval
            # returns (point, intervals) with intervals shaped (n, 2, n_confidence_levels).
            y_pred, y_pis = self.conformal.predict_interval(X)
            point = np.clip(y_pred, 0, self.cap)
            low = np.clip(y_pis[:, 0, 0], 0, self.cap)
            high = np.clip(y_pis[:, 1, 0], 0, self.cap)
        else:
            point = np.clip(self.base_model.predict(X), 0, self.cap)
            # Fallback: ±20% interval
            low = point * 0.8
            high = point * 1.2

        return {"point": point, "low": low, "high": high}

    @property
    def feature_importances_(self) -> np.ndarray:
        return self.base_model.feature_importances_


def _folds(n_samples: int, groups: np.ndarray | None) -> Any:
    """Five folds, or fewer when there is too little to split; group-aware when groups are known."""
    if groups is not None and len(np.unique(groups)) >= 2:
        from sklearn.model_selection import GroupKFold

        return GroupKFold(n_splits=min(5, len(np.unique(groups))))
    from sklearn.model_selection import KFold

    return KFold(n_splits=max(2, min(5, n_samples)), shuffle=True, random_state=42)
