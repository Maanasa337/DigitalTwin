"""Tests for the ML foundations the trainer, benchmark and edge share: per-unit windows, the public
dataset loaders, ONNX export parity (FR-EDGE-01), the on-disk bundle and the benchmark report."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from twinvoice_pdm.benchmark.cmapss import nasa_score
from twinvoice_pdm.benchmark.metropt import score_events
from twinvoice_pdm.benchmark.runner import TARGETS, check, missing_datasets, render_markdown
from twinvoice_pdm.datasets import (
    METROPT3_FAILURES,
    load_ai4i,
    load_cmapss,
    load_metropt3,
    metropt3_labels,
    normalise_operating_conditions,
)
from twinvoice_pdm.features import FeatureSpec, build_features, compute_stats, rolling_windows
from twinvoice_pdm.registry.bundle import apply_isotonic, isotonic_maps, load_bundle, load_model_pickle, save_bundle
from twinvoice_pdm.registry.onnx_export import PARITY_TOL, export_lgbm, parity, snap_thresholds

RNG = np.random.default_rng(7)


# ── Windowing ─────────────────────────────────────────────────────────


def two_units(rows: int = 40) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "unit_id": [1] * rows + [2] * rows,
            "cycle": list(range(1, rows + 1)) * 2,
            # Unit 2 sits at a different level; a window straddling both would show a huge std.
            "s_1": np.r_[np.full(rows, 1.0), np.full(rows, 100.0)],
        }
    )


def test_windows_never_cross_a_unit_boundary():
    features = build_features(two_units(), FeatureSpec(window_size=10, stride=1, stat_features=["std"]))
    assert len(features) == 2 * (40 - 10 + 1)
    assert features["s_1_std"].max() == pytest.approx(0.0)


def test_window_end_index_points_at_the_last_row_of_each_window():
    df = two_units()
    features = build_features(df, FeatureSpec(window_size=10, stride=5, stat_features=["last"]))
    ends = df.loc[features.index]
    assert (ends["cycle"] >= 10).all()
    assert features["s_1_last"].tolist() == ends["s_1"].tolist()


def test_without_the_group_column_the_frame_is_one_series():
    df = two_units().drop(columns=["unit_id"])
    features = build_features(df, FeatureSpec(window_size=10, stride=1, stat_features=["std"]), group_col=None)
    assert len(features) == 80 - 10 + 1
    assert features["s_1_std"].max() > 10


def test_vectorised_stats_match_the_reference_definitions():
    window = RNG.normal(size=50)
    stats = compute_stats(window)
    assert stats["std"] == pytest.approx(np.std(window))
    assert stats["slope"] == pytest.approx(np.polyfit(np.arange(50), window, 1)[0])
    centred = (window - window.mean()) / window.std()
    assert stats["kurtosis"] == pytest.approx(np.mean(centred**4) - 3.0)


def test_rolling_windows_stride_selects_every_nth_start():
    windows = rolling_windows(np.arange(20.0), window_size=5, stride=5)
    assert windows[:, 0, 0].tolist() == [0.0, 5.0, 10.0, 15.0]


def test_string_columns_are_not_treated_as_sensors():
    df = two_units().assign(asset_type="cnc_mill", state="RUNNING")
    features = build_features(df, FeatureSpec(window_size=10, stride=10, stat_features=["mean"]))
    assert list(features.columns) == ["s_1_mean"]


# ── Loaders ───────────────────────────────────────────────────────────


def write_cmapss(folder, subset="FD001"):
    rows = []
    for unit, length in ((1, 30), (2, 25)):
        for cycle in range(1, length + 1):
            rows.append([unit, cycle, 0.0, 0.0, 100.0, *RNG.normal(size=21)])
    text = "\n".join(" ".join(f"{v:g}" for v in row) for row in rows)
    (folder / f"train_{subset}.txt").write_text(text)
    (folder / f"test_{subset}.txt").write_text(text)
    (folder / f"RUL_{subset}.txt").write_text("7 \n12 \n")


def test_cmapss_test_rul_comes_from_the_rul_file(tmp_path):
    write_cmapss(tmp_path)
    data = load_cmapss(tmp_path, "FD001")
    test = data["test"]
    last = test.groupby("unit_id").tail(1).set_index("unit_id")["rul"]
    assert last.to_dict() == {1: 7, 2: 12}
    first_unit1 = test[(test["unit_id"] == 1) & (test["cycle"] == 1)]["rul"].iloc[0]
    assert first_unit1 == 7 + 29
    assert data["train"].groupby("unit_id")["rul"].min().eq(0).all()


def test_operating_condition_normalisation_is_fitted_on_train_only():
    train = pd.DataFrame(
        {"setting_1": [0.0] * 50 + [35.0] * 50, "setting_2": 0.0, "setting_3": 100.0,
         "s_2": np.r_[RNG.normal(10, 1, 50), RNG.normal(500, 1, 50)]}
    )  # fmt: skip
    test = train.copy()
    test["s_2"] = test["s_2"] + 1.0
    train_n, (test_n,) = normalise_operating_conditions(train, [test], ["s_2"], n_conditions=2)
    assert abs(train_n["s_2"].mean()) < 1e-6
    # The regime offset (10 vs 500) is gone; only the +1 shift, in units of each regime's std, remains.
    assert test_n["s_2"].mean() == pytest.approx(train_n["s_2"].mean() + 1.0, abs=0.3)


def test_ai4i_drops_leakage_and_one_hots_type(tmp_path):
    csv = tmp_path / "ai4i2020.csv"
    csv.write_text(
        "﻿UDI,Product ID,Type,Air temperature [K],Process temperature [K],Rotational speed [rpm],"
        "Torque [Nm],Tool wear [min],Machine failure,TWF,HDF,PWF,OSF,RNF\n"
        "1,M1,M,298.1,308.6,1551,42.8,0,0,0,0,0,0,0\n"
        "2,L2,L,298.2,308.7,1408,46.3,3,1,1,0,0,0,0\n",
        encoding="utf-8",
    )
    df = load_ai4i(tmp_path)
    assert "machine_failure" in df.columns
    assert not {"TWF", "HDF", "UDI", "Product ID", "Type"} & set(df.columns)
    assert {"type_M", "type_L"} <= set(df.columns)
    assert df["machine_failure"].tolist() == [0, 1]


def test_metropt_is_resampled_and_labelled(tmp_path):
    times = pd.date_range("2020-04-17 23:58", periods=240, freq="10s")
    frame = pd.DataFrame({"timestamp": times.astype(str)})
    for col in ["TP2", "TP3", "H1", "DV_pressure", "Reservoirs", "Oil_temperature", "Motor_current",
                "COMP", "DV_eletric", "Towers", "MPG", "LPS", "Pressure_switch", "Oil_level", "Caudal_impulses"]:
        frame[col] = 1.0
    frame.to_csv(tmp_path / "MetroPT3(AirCompressor).csv")
    df = load_metropt3(tmp_path)
    assert len(df) == 40  # 40 minutes of 10 s readings
    labels = metropt3_labels(df.index)
    assert labels[:2].tolist() == [0, 0] and labels[2:].all()
    assert len(METROPT3_FAILURES) == 4


# ── ONNX parity and bundles ───────────────────────────────────────────


def regression_problem(n: int = 600, features: int = 8):
    X = RNG.normal(size=(n, features))
    y = np.clip(120 - 40 * X[:, 0] + 10 * X[:, 1] ** 2 + RNG.normal(0, 5, n), 0, 125)
    return X, y


def test_onnx_regressor_matches_lightgbm_within_tolerance(tmp_path):
    import lightgbm as lgb

    X, y = regression_problem()
    model = snap_thresholds(lgb.LGBMRegressor(n_estimators=200, verbose=-1).fit(X, y))
    path = export_lgbm(model, X.shape[1], tmp_path / "m.onnx")
    result = parity(model, path, X)
    assert result.passed, result.max_abs
    assert result.max_abs <= PARITY_TOL


def test_onnx_classifier_probabilities_match(tmp_path):
    import lightgbm as lgb

    X, y = regression_problem()
    labels = np.where(y > 100, "worn", "ok")
    model = snap_thresholds(lgb.LGBMClassifier(n_estimators=100, verbose=-1).fit(X, labels))
    path = export_lgbm(model, X.shape[1], tmp_path / "c.onnx")
    assert parity(model, path, X).passed


def test_bundle_round_trip(tmp_path):
    import lightgbm as lgb

    X, y = regression_problem()
    model = lgb.LGBMRegressor(n_estimators=80, verbose=-1).fit(X, y)
    names = [f"s{i}_mean" for i in range(X.shape[1])]
    spec = FeatureSpec(window_size=12, stride=3, stat_features=["mean"], sensor_cols=[f"s{i}" for i in range(8)])
    bundle = save_bundle(
        tmp_path / "b", model=model, task="rul", feature_names=names, spec=spec, background=X, conformal_q=9.5
    )
    assert bundle.parity_max_abs is not None and bundle.parity_max_abs <= PARITY_TOL

    loaded = load_bundle(tmp_path / "b")
    assert loaded.feature_names == names
    assert loaded.spec == spec
    assert loaded.meta["conformal_q"] == 9.5
    assert json.loads((tmp_path / "b" / "bundle.json").read_text())["task"] == "rul"
    artifact = load_model_pickle(tmp_path / "b")
    assert {"model", "background"} <= set(artifact)
    assert np.allclose(artifact["model"].predict(X[:5]), model.predict(X[:5]))
    booster = lgb.Booster(model_file=str(loaded.booster_path))
    assert np.allclose(booster.predict(X[:5]), model.predict(X[:5]))


def test_isotonic_maps_reproduce_a_monotone_calibration():
    p = RNG.uniform(size=500)
    raw = np.column_stack([p, 1 - p])
    calibrated = np.column_stack([raw[:, 0] ** 2, 1 - raw[:, 0] ** 2])
    out = apply_isotonic(raw, isotonic_maps(raw, calibrated))
    assert np.allclose(out.sum(axis=1), 1.0)
    assert np.all(np.diff(out[np.argsort(raw[:, 0]), 0]) >= -1e-9)


# ── Benchmark pieces ──────────────────────────────────────────────────


def test_nasa_score_penalises_late_predictions_harder():
    assert nasa_score(np.array([50.0]), np.array([60.0])) > nasa_score(np.array([50.0]), np.array([40.0]))
    assert nasa_score(np.array([50.0]), np.array([50.0])) == 0.0


def test_event_scoring_counts_detections_lead_time_and_false_alarms():
    failure = METROPT3_FAILURES[0]
    events = [
        (failure.start - pd.Timedelta(hours=5), failure.start - pd.Timedelta(hours=4)),  # early warning
        (pd.Timestamp("2020-03-01"), pd.Timestamp("2020-03-01 02:00")),  # false alarm
    ]
    scores = score_events(events, [failure], pd.Timestamp("2020-02-01"))
    assert scores["event_recall"] == 1.0
    assert scores["event_precision"] == 0.5
    assert scores["mean_lead_time_h"] == pytest.approx(5.0)


def test_report_marks_pass_and_fail_against_targets():
    report = render_markdown({"FD001": {"rmse": 12.0, "nasa_score": 400.0}}, meta={"seed": 42, "quick": False})
    assert "| FD001 | rmse | 12 | ≤ 13 | pass |" in report
    assert "| FD001 | nasa_score | 400 | ≤ 300 | **fail** |" in report
    assert check(0.97, TARGETS["AI4I"]["auc"])


def test_missing_raw_data_is_reported_by_download_name(tmp_path):
    (tmp_path / "ai4i").mkdir()
    (tmp_path / "ai4i" / "ai4i2020.csv").write_text("x")
    assert missing_datasets(["FD001", "FD002", "AI4I", "METROPT3"], tmp_path) == ["cmapss", "metropt3"]


def test_anomaly_forest_exports_with_the_same_scores(tmp_path):
    import lightgbm as lgb

    from twinvoice_pdm.anomaly import AnomalyDetector
    from twinvoice_pdm.registry.onnx_export import onnx_anomaly_raw, onnx_session

    X, y = regression_problem()
    detector = AnomalyDetector(n_estimators=50).fit(X)
    model = lgb.LGBMRegressor(n_estimators=20, verbose=-1).fit(X, y)
    names = [f"f{i}" for i in range(X.shape[1])]
    bundle = save_bundle(
        tmp_path / "b", model=model, task="rul", feature_names=names, spec=FeatureSpec(), background=X, anomaly=detector
    )
    assert bundle.anomaly_path is not None
    raw = onnx_anomaly_raw(onnx_session(bundle.anomaly_path), X, bundle.meta["anomaly_offset"])
    assert np.allclose(raw, -detector.model.score_samples(X.astype(np.float32)), atol=1e-4)
    assert bundle.meta["anomaly_baseline_q95"] == pytest.approx(detector._baseline_q95)
