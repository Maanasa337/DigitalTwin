"""A tiny but real model bundle, trained here, so the tests exercise the same files `make train` writes."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from twinvoice_pdm.anomaly import AnomalyDetector
from twinvoice_pdm.features import FeatureSpec, build_features
from twinvoice_pdm.registry.bundle import save_bundle
from twinvoice_pdm.rul import RulEstimator

SENSORS = ["spindle.vib_rms", "spindle.temp"]
SPEC = FeatureSpec(window_size=6, stride=3, stat_features=["mean", "std", "slope", "last"], sensor_cols=SENSORS)
MODEL_NAME = "rul-synthetic-cnc_mill"
VERSION = "2026.09.21-100000"


def telemetry(rows: int = 400, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    wear = np.linspace(0, 1, rows)
    return pd.DataFrame(
        {
            "spindle.vib_rms": 2 + 3 * wear + rng.normal(0, 0.1, rows),
            "spindle.temp": 50 + 10 * wear + rng.normal(0, 0.5, rows),
            "true_rul_d": 80 * (1 - wear),
        }
    )


@pytest.fixture(scope="session")
def model_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("models")
    df = telemetry()
    features = build_features(df, SPEC, group_col=None)
    y = df.loc[features.index, "true_rul_d"].to_numpy()
    X = features.to_numpy()

    estimator = RulEstimator(n_estimators=40, cap=90).fit(X, y, conformal=False)
    anomaly = AnomalyDetector(n_estimators=30).fit(X[: len(X) // 2])
    save_bundle(
        root / MODEL_NAME / VERSION,
        model=estimator.base_model,
        task="rul",
        feature_names=list(features.columns),
        spec=SPEC,
        background=X,
        conformal_q=4.0,
        coverage=0.9,
        rul_cap=90.0,
        anomaly=anomaly,
        extra={"rul_unit": "d", "name": MODEL_NAME},
    )
    return root
