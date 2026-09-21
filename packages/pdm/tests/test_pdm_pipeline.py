"""Tests for the M5 predictive-maintenance library.

This module previously imported a `pdm.*` package with functions that have never existed
(`generate_synthetic_telemetry`, `extract_sliding_window_features`, `RulRegressor`), so the file
could not be collected and `packages/pdm` had no working tests at all. It is rewritten against the
API the package actually exposes: `twinvoice_pdm.{datasets,features,anomaly,failure,rul}`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from twinvoice_pdm.anomaly import AnomalyDetector
from twinvoice_pdm.datasets import load_synthetic
from twinvoice_pdm.failure import FailureClassifier
from twinvoice_pdm.features import FeatureSpec, build_features, compute_stats, rolling_windows
from twinvoice_pdm.rul import RUL_CAP, RulEstimator, cap_rul

RNG = np.random.default_rng(42)


def telemetry(rows: int = 300, drift: float = 0.0) -> pd.DataFrame:
    """A healthy vibration/temperature trace, optionally drifting upward as wear would."""
    ramp = np.linspace(0.0, drift, rows)
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-09-01", periods=rows, freq="s"),
            "vib_rms": 2.0 + ramp + RNG.normal(0, 0.05, rows),
            "temp": 55.0 + 2 * ramp + RNG.normal(0, 0.2, rows),
        }
    )


# ── Windowing and statistics ──────────────────────────────────────────

def test_rolling_windows_shape_follows_window_and_stride():
    windows = rolling_windows(np.arange(100.0), window_size=20, stride=10)
    assert windows.shape == (9, 20, 1)


def test_a_series_shorter_than_one_window_produces_none():
    """Fewer samples than the window is not an error; there is simply nothing to score yet."""
    assert rolling_windows(np.arange(5.0), window_size=20, stride=10).shape[0] == 0


def test_compute_stats_reports_the_expected_statistics():
    stats = compute_stats(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert stats["mean"] == pytest.approx(3.0)
    assert stats["min"] == 1.0
    assert stats["max"] == 5.0
    assert stats["rms"] == pytest.approx(np.sqrt(np.mean(np.square([1, 2, 3, 4, 5]))))
    # A straight ramp has a slope of exactly one sample per step.
    assert stats["slope"] == pytest.approx(1.0, abs=1e-6)


def test_a_constant_window_has_no_spread_and_no_slope():
    stats = compute_stats(np.full(30, 4.2))
    assert stats["std"] == pytest.approx(0.0)
    assert stats["slope"] == pytest.approx(0.0, abs=1e-9)


def test_build_features_names_columns_by_sensor_and_statistic():
    frame = build_features(telemetry(200), FeatureSpec(window_size=50, stride=25))
    assert not frame.empty
    assert "vib_rms_mean" in frame.columns
    assert "temp_std" in frame.columns
    # `time` is not a sensor and must not become a feature.
    assert not any(column.startswith("time") for column in frame.columns)


def test_build_features_returns_empty_rather_than_raising_on_a_short_frame():
    assert build_features(telemetry(10), FeatureSpec(window_size=60, stride=10)).empty


def test_sensor_columns_can_be_restricted():
    frame = build_features(telemetry(200), FeatureSpec(window_size=50, stride=25, sensor_cols=["vib_rms"]))
    assert all(column.startswith("vib_rms") for column in frame.columns)


# ── Anomaly detection and health index ────────────────────────────────

def test_health_index_falls_as_the_signal_degrades():
    """The point of the health index: a worn machine must score lower than a healthy one."""
    healthy = build_features(telemetry(400), FeatureSpec(window_size=50, stride=25)).values
    degraded = build_features(telemetry(400, drift=3.0), FeatureSpec(window_size=50, stride=25)).values

    detector = AnomalyDetector(contamination=0.05).fit(healthy)
    assert detector.health_index(healthy).mean() > detector.health_index(degraded).mean()


def test_health_index_stays_inside_its_stated_range():
    features = build_features(telemetry(400), FeatureSpec(window_size=50, stride=25)).values
    detector = AnomalyDetector().fit(features)
    health = detector.health_index(features)
    assert health.min() >= 0.0
    assert health.max() <= 100.0


def test_anomaly_scores_are_normalised():
    features = build_features(telemetry(400), FeatureSpec(window_size=50, stride=25)).values
    scores = AnomalyDetector().fit(features).score(features)
    assert scores.min() >= 0.0
    assert scores.max() <= 1.0


# ── RUL target and estimator ──────────────────────────────────────────

def test_rul_is_capped_piecewise_linearly():
    """The C-MAPSS convention: remaining life above the cap is not distinguishable."""
    capped = cap_rul(np.array([-5.0, 0.0, 50.0, 300.0]))
    assert capped.tolist() == [0.0, 0.0, 50.0, float(RUL_CAP)]


def test_rul_estimator_produces_a_point_inside_its_interval():
    features = RNG.normal(size=(200, 4))
    target = 120 - 40 * features[:, 0] + RNG.normal(0, 2, 200)

    estimator = RulEstimator(n_estimators=40).fit(features, target, conformal=False)
    prediction = estimator.predict(features[:20])

    assert set(prediction) >= {"point", "low", "high"}
    assert len(prediction["point"]) == 20
    assert np.all(prediction["low"] <= prediction["point"] + 1e-6)
    assert np.all(prediction["point"] <= prediction["high"] + 1e-6)


def test_rul_predictions_respect_the_cap():
    features = RNG.normal(size=(150, 3))
    target = np.full(150, 400.0)
    estimator = RulEstimator(n_estimators=30).fit(features, target, conformal=False)
    assert estimator.predict(features[:10])["point"].max() <= RUL_CAP + 1


def test_conformal_intervals_are_available():
    features = RNG.normal(size=(200, 4))
    target = 120 - 40 * features[:, 0] + RNG.normal(0, 2, 200)

    estimator = RulEstimator(n_estimators=40).fit(features, target, conformal=True)
    prediction = estimator.predict(features[:20])

    assert estimator.conformal is not None
    assert np.all(prediction["low"] <= prediction["point"] + 1e-6)
    assert np.all(prediction["point"] <= prediction["high"] + 1e-6)
    # A conformal interval has to be narrower than the whole RUL range to be worth showing.
    assert np.median(prediction["high"] - prediction["low"]) < RUL_CAP


def test_conformal_intervals_achieve_their_nominal_coverage():
    """FR-PM-06 asks for 90% intervals *with reported empirical coverage*, not just any interval."""
    train_x = RNG.normal(size=(400, 4))
    train_y = 120 - 40 * train_x[:, 0] + RNG.normal(0, 5, 400)
    test_x = RNG.normal(size=(300, 4))
    test_y = np.clip(120 - 40 * test_x[:, 0] + RNG.normal(0, 5, 300), 0, RUL_CAP)

    estimator = RulEstimator(n_estimators=60, coverage=0.90).fit(train_x, train_y, conformal=True)
    prediction = estimator.predict(test_x)

    covered = (prediction["low"] <= test_y) & (test_y <= prediction["high"])
    # Split-conformal coverage is finite-sample valid, so it lands near nominal from above; the
    # band allows for the clipping at the RUL cap and 300 test points of sampling noise.
    assert 0.85 <= covered.mean() <= 0.99


def test_conformal_is_skipped_when_there_is_too_little_history():
    """Cold start: a handful of windows cannot calibrate, and must not crash the fit either."""
    features = RNG.normal(size=(6, 3))
    target = np.array([100.0, 90.0, 80.0, 70.0, 60.0, 50.0])

    estimator = RulEstimator(n_estimators=10).fit(features, target, conformal=True)

    assert estimator.conformal is None
    prediction = estimator.predict(features)
    assert np.all(prediction["low"] <= prediction["high"])


# ── Failure classification ────────────────────────────────────────────

def test_failure_classifier_returns_a_probability_per_class():
    features = RNG.normal(size=(180, 4))
    labels = np.where(features[:, 0] > 0.4, "bearing_wear", "none")
    labels[:10] = "tool_wear"

    classifier = FailureClassifier(n_estimators=40).fit(features, labels, calibrate=False)
    probabilities = classifier.predict_proba(features[:15])

    assert probabilities.shape == (15, len(classifier.classes_))
    assert np.allclose(probabilities.sum(axis=1), 1.0)
    assert set(classifier.classes_) == {"none", "bearing_wear", "tool_wear"}


def test_calibration_keeps_the_probabilities_a_distribution():
    """Calibration is what makes the failure probability mean what it says (FR-PM-04)."""
    features = RNG.normal(size=(300, 4))
    labels = np.where(
        features[:, 0] > 0.5, "bearing_wear", np.where(features[:, 0] < -0.5, "tool_wear", "none")
    )

    classifier = FailureClassifier(n_estimators=40).fit(features, labels, calibrate=True)
    probabilities = classifier.predict_proba(features[:20])
    assert np.allclose(probabilities.sum(axis=1), 1.0)
    assert probabilities.min() >= 0.0


def test_calibration_works_for_an_asset_with_a_single_failure_mode():
    features = RNG.normal(size=(240, 4))
    labels = np.where(features[:, 0] > 0.0, "bearing_wear", "none")

    classifier = FailureClassifier(n_estimators=40).fit(features, labels, calibrate=True)
    assert classifier.predict_proba(features[:5]).shape == (5, 2)


# ── Dataset loading ───────────────────────────────────────────────────

def test_loading_from_a_missing_export_directory_says_so(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_synthetic(tmp_path / "nope")


def test_an_empty_export_directory_is_reported_as_empty(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_synthetic(tmp_path)


def test_parquet_exports_are_concatenated_and_time_ordered(tmp_path):
    telemetry(50).iloc[25:].to_parquet(tmp_path / "b.parquet")
    telemetry(50).iloc[:25].to_parquet(tmp_path / "a.parquet")

    combined = load_synthetic(tmp_path)
    assert len(combined) == 50
    assert combined["time"].is_monotonic_increasing


def test_loading_can_filter_to_one_asset(tmp_path):
    frame = telemetry(40)
    frame["asset_code"] = ["cnc-01"] * 20 + ["cnc-02"] * 20
    frame.to_parquet(tmp_path / "mixed.parquet")

    assert set(load_synthetic(tmp_path, asset_code="cnc-01")["asset_code"]) == {"cnc-01"}
