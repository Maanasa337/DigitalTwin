"""TreeSHAP on the device, on the bundle's native LightGBM booster (booster.txt).

The explainer is built once per model and reused: constructing `shap.TreeExplainer` walks every tree
and costs far more than one explanation, which is exactly the number FR-EDGE-02 asks us to log.
Attribution ranking and labels are `twinvoice_xai`'s, so an edge explanation reads the same as a
server one.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from twinvoice_xai.attribution import ExplanationResult, _select_output, build_attributions


class LocalExplainer:
    def __init__(self, booster_path: Path | str, feature_names: list[str]) -> None:
        import lightgbm as lgb
        import shap

        self.feature_names = feature_names
        self.booster = lgb.Booster(model_file=str(booster_path))
        self.explainer = shap.TreeExplainer(self.booster)

    def explain(self, x: np.ndarray, top_k: int = 8) -> tuple[ExplanationResult, float]:
        """Attributions for one feature vector (top ``top_k`` kept), and the time it took in ms."""
        started = time.perf_counter()
        X = np.asarray(x, dtype=float).reshape(1, -1)
        values, base = _select_output(self.explainer.shap_values(X), self.explainer.expected_value, None)
        attributions = build_attributions(self.feature_names, X[0], values)[:top_k]
        elapsed = (time.perf_counter() - started) * 1000
        return ExplanationResult("tree_shap", base, attributions, compute_ms=int(elapsed)), elapsed
