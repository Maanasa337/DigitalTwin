"""C-MAPSS FD001-FD004 RUL benchmark: LightGBM on windowed features with CV+ conformal intervals.

Protocol (the one the published numbers in PRD §4.5 use):
  * piecewise-linear target capped at 125 cycles;
  * the official test split, scored on each test engine's *last* window against RUL_FD00x.txt;
  * CV+ folds grouped by engine, so no engine is on both sides of a calibration split.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from twinvoice_pdm.datasets import CMAPSS_SENSORS, cmapss_dir, load_cmapss, normalise_operating_conditions
from twinvoice_pdm.features import FeatureSpec, build_features
from twinvoice_pdm.rul import RUL_CAP, RulEstimator

SUBSETS = ("FD001", "FD002", "FD003", "FD004")
# FD002 and FD004 fly six operating regimes; FD001 and FD003 one.
MULTI_CONDITION = frozenset({"FD002", "FD004"})
WINDOW = 30
STATS = ["mean", "std", "slope", "last", "min", "max"]
# A sensor whose training std is below this is a constant: it cannot carry wear information.
CONSTANT_STD = 1e-3


def nasa_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """PHM08 scoring function: late predictions (d > 0) are penalised harder than early ones."""
    d = np.asarray(y_pred, dtype=float) - np.asarray(y_true, dtype=float)
    return float(np.sum(np.where(d < 0, np.exp(-d / 13.0) - 1.0, np.exp(d / 10.0) - 1.0)))


def _pad_front(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """Repeat each engine's first row so even a 31-cycle test engine yields a full window.

    Padded rows get negative cycle numbers and no label use: only windows that end on a real cycle
    are kept, the padding only fills their history.
    """
    frames = []
    for _, unit in df.groupby("unit_id", sort=False):
        pad = pd.concat([unit.iloc[[0]]] * (window - 1), ignore_index=True)
        pad["cycle"] = unit["cycle"].iloc[0] - np.arange(window - 1, 0, -1)
        pad["padded"] = True
        unit = unit.assign(padded=False)
        frames.append(pd.concat([pad, unit], ignore_index=True))
    return pd.concat(frames, ignore_index=True)


def windowed(df: pd.DataFrame, sensors: list[str], window: int = WINDOW) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Features per window end, plus the rows those windows end on (unit_id, cycle, rul)."""
    padded = _pad_front(df, window)
    spec = FeatureSpec(window_size=window, stride=1, stat_features=STATS, sensor_cols=sensors)
    features = build_features(padded, spec, group_col="unit_id")
    ends = padded.loc[features.index]
    keep = ~ends["padded"].to_numpy()
    features, ends = features[keep], ends[keep]
    # Age in cycles is observable at inference time (the engine's own counter) and a strong prior.
    features = features.assign(cycle=ends["cycle"].to_numpy())
    return features.reset_index(drop=True), ends.reset_index(drop=True)


def prepare(raw_dir: Path | str, subset: str, *, seed: int = 42, quick: bool = False) -> dict[str, Any]:
    data = load_cmapss(cmapss_dir(raw_dir), subset)
    train, test = data["train"], data["test"]
    if quick:
        # A handful of engines keeps the smoke run in seconds; the protocol is otherwise identical.
        train = train[train["unit_id"] <= 25]
        test = test[test["unit_id"] <= 25]

    sensors = list(CMAPSS_SENSORS)
    if subset in MULTI_CONDITION:
        train, (test,) = normalise_operating_conditions(train, [test], sensors, seed=seed)
    sensors = [s for s in sensors if train[s].std() > CONSTANT_STD]

    x_train, train_rows = windowed(train, sensors)
    x_test, test_rows = windowed(test, sensors)
    last = test_rows.groupby("unit_id")["cycle"].idxmax().to_numpy()
    return {
        "sensors": sensors,
        "x_train": x_train,
        "y_train": train_rows["rul"].to_numpy(dtype=float),
        "groups": train_rows["unit_id"].to_numpy(),
        "x_test": x_test.loc[last],
        "y_test": test_rows.loc[last, "rul"].to_numpy(dtype=float),
    }


def run(raw_dir: Path | str, subset: str, *, seed: int = 42, quick: bool = False) -> dict[str, float]:
    """Train on the subset's training engines and score the official test engines."""
    prepared = prepare(raw_dir, subset, seed=seed, quick=quick)
    estimator = RulEstimator(
        n_estimators=60 if quick else 700,
        max_depth=6,
        learning_rate=0.1 if quick else 0.02,
        random_state=seed,
        coverage=0.90,
    )
    estimator.base_model.set_params(num_leaves=31, min_child_samples=40, subsample=0.8, subsample_freq=1,
                                    colsample_bytree=0.7)
    estimator.fit(prepared["x_train"].to_numpy(), prepared["y_train"], conformal=True, groups=prepared["groups"])

    prediction = estimator.predict(prepared["x_test"].to_numpy())
    # The test truth is capped too: the model cannot know an engine has 140 rather than 125 cycles left.
    truth = np.clip(prepared["y_test"], 0, RUL_CAP)
    point, low, high = prediction["point"], prediction["low"], prediction["high"]
    return {
        "rmse": float(np.sqrt(np.mean((point - truth) ** 2))),
        "nasa_score": nasa_score(truth, point),
        "coverage_90": float(np.mean((low <= truth) & (truth <= high))),
        "interval_width": float(np.mean(high - low)),
        "n_test_units": float(len(truth)),
    }
