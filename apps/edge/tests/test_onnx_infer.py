"""ONNX inference and local TreeSHAP on a trained bundle agree with the native model (FR-EDGE-01/02)."""

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pytest
from twinvoice_pdm.features import build_features
from twinvoice_pdm.registry.bundle import load_model_pickle

from edge.config import parse_assets
from edge.features import RollingWindow
from edge.onnx_infer import EdgeModel, latest_bundle_dir
from edge.treeshap_local import LocalExplainer
from tests.conftest import MODEL_NAME, SENSORS, SPEC, VERSION, telemetry


@pytest.fixture(scope="module")
def model(model_dir: Path) -> EdgeModel:
    return EdgeModel(latest_bundle_dir(model_dir, MODEL_NAME))


def test_the_newest_bundle_is_picked_and_named(model: EdgeModel) -> None:
    assert model.model_version == f"{MODEL_NAME}:{VERSION}"


def test_onnx_rul_matches_the_native_model_within_1e4(model: EdgeModel, model_dir: Path) -> None:
    native = load_model_pickle(model_dir / MODEL_NAME / VERSION)["model"]
    X = build_features(telemetry(seed=9), SPEC, group_col=None).to_numpy()
    for row in X[:20]:
        expected = float(np.clip(native.predict(row.astype(np.float32).astype(float).reshape(1, -1))[0], 0, 90))
        assert model.predict(row).rul["point"] == pytest.approx(expected, abs=1e-4)


def test_interval_is_the_conformal_half_width_and_health_is_bounded(model: EdgeModel) -> None:
    x = build_features(telemetry(seed=5), SPEC, group_col=None).to_numpy()[10]
    out = model.predict(x)
    rul = out.rul
    assert rul["unit"] == "d"
    assert rul["high"] - rul["point"] == pytest.approx(4.0, abs=1e-6) or rul["high"] == 90.0
    assert out.health_index is not None and 0 <= out.health_index <= 100
    assert out.infer_ms > 0


def test_rolling_window_features_equal_build_features_on_the_same_samples(model: EdgeModel) -> None:
    df = telemetry(seed=11)
    window = RollingWindow(SPEC, model.feature_names)
    due = [window.add(None, {s: df.at[i, s] for s in SENSORS}) for i in range(SPEC.window_size)]  # type: ignore[arg-type]
    assert due[-1] and not any(due[:-1])
    expected = build_features(df.iloc[: SPEC.window_size], SPEC, group_col=None).iloc[0].to_numpy()
    assert np.allclose(window.vector(), expected)
    # Then one emission every `stride` samples.
    more = [window.add(None, {s: df.at[i, s] for s in SENSORS}) for i in range(6, 12)]  # type: ignore[arg-type]
    assert more == [False, False, True, False, False, True]


def test_a_missing_reading_is_carried_forward(model: EdgeModel) -> None:
    window = RollingWindow(SPEC, model.feature_names)
    window.add(None, {"spindle.vib_rms": 2.0, "spindle.temp": 50.0})  # type: ignore[arg-type]
    window.add(None, {"spindle.vib_rms": None, "spindle.temp": 51.0})  # type: ignore[arg-type]
    assert window._rows[-1][1]["spindle.vib_rms"] == 2.0


def test_local_treeshap_attributions_add_up_to_the_prediction(model: EdgeModel) -> None:
    explainer = LocalExplainer(model.bundle.booster_path, model.feature_names)
    x = build_features(telemetry(seed=2), SPEC, group_col=None).to_numpy()[5]
    result, ms = explainer.explain(x, top_k=len(model.feature_names))
    raw = lgb.Booster(model_file=str(model.bundle.booster_path)).predict(x.reshape(1, -1))[0]
    assert result.base_value + sum(a.contribution for a in result.attributions) == pytest.approx(raw, abs=1e-3)
    assert ms >= 0
    top3 = explainer.explain(x, top_k=3)[0]
    assert len(top3.attributions) == 3


def test_asset_bindings_default_from_the_code_prefix() -> None:
    bindings = parse_assets("cnc-01, press-01, conveyor-02=my-model")
    assert [(b.code, b.model_name) for b in bindings] == [
        ("cnc-01", "rul-synthetic-cnc_mill"),
        ("press-01", "rul-synthetic-hydraulic_press"),
        ("conveyor-02", "my-model"),
    ]
    with pytest.raises(ValueError):
        parse_assets("robot-01")
