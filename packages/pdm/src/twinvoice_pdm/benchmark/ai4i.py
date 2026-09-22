"""AI4I 2020 failure-classification benchmark: stratified 5-fold LightGBM with class weights.

Metrics are computed on out-of-fold predictions, so every row is scored by a model that never saw it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from twinvoice_pdm.datasets import AI4I_TARGET, load_ai4i

N_FOLDS = 5
ECE_BINS = 10


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = ECE_BINS) -> float:
    """Weighted mean |accuracy - confidence| over equal-width probability bins (binary, positive class)."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    ece = 0.0
    for b in range(bins):
        mask = idx == b
        if mask.any():
            ece += mask.mean() * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(ece)


def run(raw_dir: Path | str, *, seed: int = 42, quick: bool = False) -> dict[str, float]:
    import lightgbm as lgb
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import f1_score, roc_auc_score
    from sklearn.model_selection import StratifiedKFold

    df = load_ai4i(Path(raw_dir) / "ai4i")
    if quick:
        df = df.sample(n=3000, random_state=seed)
    y = df.pop(AI4I_TARGET).to_numpy()
    X = df.to_numpy(dtype=float)

    oof = np.zeros(len(y))
    folds = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    for train_idx, test_idx in folds.split(X, y):
        base = lgb.LGBMClassifier(
            n_estimators=60 if quick else 400,
            learning_rate=0.05,
            num_leaves=15,
            min_child_samples=10,
            class_weight="balanced",
            random_state=seed,
            verbose=-1,
        )
        # Class weights buy recall on the 3.4 % positive class but inflate the raw probabilities;
        # isotonic calibration inside the fold brings them back to frequencies (the ECE below).
        model = CalibratedClassifierCV(base, method="isotonic", cv=3)
        model.fit(X[train_idx], y[train_idx])
        oof[test_idx] = model.predict_proba(X[test_idx])[:, 1]

    # F1 at the threshold that maximises it on the out-of-fold scores, reported with the threshold.
    thresholds = np.linspace(0.05, 0.95, 91)
    f1s = [f1_score(y, (oof >= t).astype(int), zero_division=0) for t in thresholds]
    best = int(np.argmax(f1s))
    return {
        "auc": float(roc_auc_score(y, oof)),
        "f1": float(f1s[best]),
        "f1_threshold": float(thresholds[best]),
        "ece": expected_calibration_error(y, oof),
        "n_rows": float(len(y)),
    }
