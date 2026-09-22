"""ONNX export of LightGBM models and the native-vs-ONNX parity check (FR-EDGE-01).

Needs the ``onnx`` extra: ``twinvoice-pdm[onnx]``.

ONNX tree ensembles hold thresholds as float32; LightGBM holds them as float64. An input that
lands between a threshold and its float32 rounding takes a different branch in each runtime, which
shows up as a jump of a whole leaf value, far beyond the 1e-4 tolerance. ``snap_thresholds`` rounds
the native model's thresholds to float32 before export, so both runtimes compare against the same
number and only float32 summation error remains.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

PARITY_TOL = 1e-4
INPUT_NAME = "input"


@dataclass(frozen=True)
class ParityResult:
    max_abs: float
    tol: float
    n: int

    @property
    def passed(self) -> bool:
        return self.max_abs <= self.tol


def snap_thresholds(model: Any) -> Any:
    """Round every split threshold of a fitted LGBM sklearn model to float32, in place.

    Moves each threshold by under one float32 ulp, so the model's decisions on float32 inputs
    (what ONNX sees) are unchanged in all but a measure-zero set of values.
    """
    import lightgbm as lgb

    booster = model.booster_
    lines = []
    for line in booster.model_to_string().splitlines():
        if line.startswith("threshold="):
            values = [repr(float(np.float32(float(v)))) for v in line.split("=", 1)[1].split()]
            line = "threshold=" + " ".join(values)
        elif line.startswith("tree_sizes="):
            # Byte offsets of each tree; stale once a threshold's text length changes, and optional.
            continue
        lines.append(line)
    model._Booster = lgb.Booster(model_str="\n".join(lines) + "\n")
    return model


def export_lgbm(model: Any, n_features: int, path: Path | str) -> Path:
    """Convert a fitted LGBMRegressor/LGBMClassifier to ONNX at ``path``.

    Classifiers are exported without ZipMap, so the second output is a plain (n, n_classes)
    probability tensor that onnxruntime can hand back as an array.
    """
    from onnxmltools import convert_lightgbm
    from onnxmltools.convert.common.data_types import FloatTensorType

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx_model = convert_lightgbm(
        model,
        name=type(model).__name__,
        initial_types=[(INPUT_NAME, FloatTensorType([None, n_features]))],
        zipmap=False,
    )
    path.write_bytes(onnx_model.SerializeToString())
    return path


def onnx_session(path: Path | str) -> Any:
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.log_severity_level = 3  # ORT warns about the label output's static shape on every batch.
    return ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])


def onnx_predict(session: Any, X: np.ndarray) -> np.ndarray:
    """Regression values (n,) or class probabilities (n, k), whichever the model produces."""
    outputs = session.run(None, {INPUT_NAME: np.asarray(X, dtype=np.float32)})
    # Classifier graphs emit (label, probabilities); regressors a single (n, 1) variable.
    return np.asarray(outputs[1]) if len(outputs) > 1 else np.asarray(outputs[0]).reshape(-1)


def native_predict(model: Any, X: np.ndarray) -> np.ndarray:
    X32 = np.asarray(X, dtype=np.float32).astype(np.float64)
    return model.predict_proba(X32) if hasattr(model, "predict_proba") else model.predict(X32)


def parity(model: Any, onnx_path: Path | str, X: np.ndarray, tol: float = PARITY_TOL) -> ParityResult:
    """Max absolute difference between native LightGBM and ONNX Runtime on the same float32 inputs."""
    onnx_out = onnx_predict(onnx_session(onnx_path), X)
    native = native_predict(model, X)
    max_abs = float(np.max(np.abs(onnx_out - native))) if len(native) else 0.0
    return ParityResult(max_abs=max_abs, tol=tol, n=len(native))


def export_isolation_forest(model: Any, n_features: int, path: Path | str) -> Path:
    """Convert a fitted sklearn IsolationForest; the graph's ``scores`` output is `decision_function`.

    `AnomalyDetector` works on ``-score_samples`` = ``-(decision_function + offset_)``, so the bundle
    records ``offset_`` next to the baseline quantile for the edge to undo.
    """
    from skl2onnx import to_onnx

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx_model = to_onnx(
        model, np.zeros((1, n_features), dtype=np.float32), target_opset={"": 17, "ai.onnx.ml": 3}
    )
    path.write_bytes(onnx_model.SerializeToString())
    return path


def onnx_anomaly_raw(session: Any, X: np.ndarray, offset: float) -> np.ndarray:
    """``-score_samples`` from an exported IsolationForest (higher = more anomalous)."""
    name = session.get_inputs()[0].name
    scores = session.run(None, {name: np.asarray(X, dtype=np.float32)})[1].reshape(-1)
    return -(scores + offset)
