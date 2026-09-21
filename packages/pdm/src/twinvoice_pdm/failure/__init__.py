"""Failure classification: LightGBM multiclass with isotonic calibration."""

from __future__ import annotations

import numpy as np

try:
    import lightgbm as lgb
except ImportError:
    lgb = None  # type: ignore[assignment]

from sklearn.calibration import CalibratedClassifierCV


class FailureClassifier:
    """LightGBM multiclass classifier for failure mode prediction.

    Classes: ``['none', <failure_mode_1>, ..., <failure_mode_n>]``
    After calibration, ``predict_proba`` returns isotonic-calibrated probabilities.
    """

    def __init__(
        self,
        n_estimators: int = 300,
        max_depth: int = 6,
        learning_rate: float = 0.05,
        random_state: int = 42,
    ) -> None:
        if lgb is None:
            raise ImportError("lightgbm is required for FailureClassifier")
        # The objective is set at fit time from the class count: LightGBM rejects `multiclass` for
        # a two-class problem, which is exactly what an asset with a single failure mode produces.
        self.base_model = lgb.LGBMClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_state=random_state,
            verbose=-1,
        )
        self.calibrated_model: CalibratedClassifierCV | None = None
        self.classes_: np.ndarray = np.array([])

    def fit(self, X: np.ndarray, y: np.ndarray, calibrate: bool = True) -> FailureClassifier:
        """Fit the classifier. If calibrate=True, wraps with isotonic calibration (CV=3)."""
        n_classes = len(np.unique(y))
        self.base_model.set_params(objective="binary" if n_classes <= 2 else "multiclass")
        self.base_model.fit(X, y)
        self.classes_ = self.base_model.classes_
        if calibrate:
            self.calibrated_model = CalibratedClassifierCV(
                estimator=self.base_model, method="isotonic", cv=3
            )
            self.calibrated_model.fit(X, y)
            self.classes_ = self.calibrated_model.classes_
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return calibrated class probabilities."""
        model = self.calibrated_model or self.base_model
        return model.predict_proba(X)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Return predicted class labels."""
        model = self.calibrated_model or self.base_model
        return model.predict(X)

    def predict_dict(self, X: np.ndarray) -> list[dict[str, float]]:
        """Return list of {class_name: probability} dicts."""
        proba = self.predict_proba(X)
        return [
            {str(cls): float(p) for cls, p in zip(self.classes_, row, strict=True)}
            for row in proba
        ]

    @property
    def feature_importances_(self) -> np.ndarray:
        return self.base_model.feature_importances_
