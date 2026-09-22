"""Model bundle on disk: the one layout the trainer writes and the explainer, API and edge read.

    {dir}/model.pkl     {"model": fitted estimator, "background": sample rows}  (explain worker)
    {dir}/model.onnx    ONNX graph of the same estimator                         (edge, download)
    {dir}/booster.txt   native LightGBM text model                               (edge TreeSHAP)
    {dir}/anomaly.onnx  optional IsolationForest for the health index            (edge)
    {dir}/bundle.json   everything else needed to turn raw outputs into a prediction

bundle.json holds plain numbers only, so the edge needs neither MAPIE nor scikit-learn's
calibrators: the conformal interval is ``point ± conformal_q`` and calibration is a piecewise-linear
isotonic map applied with ``np.interp``.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from twinvoice_pdm.features import FeatureSpec

BUNDLE_VERSION = 1
MODEL_PKL = "model.pkl"
MODEL_ONNX = "model.onnx"
BOOSTER_TXT = "booster.txt"
ANOMALY_ONNX = "anomaly.onnx"
BUNDLE_JSON = "bundle.json"
BACKGROUND_ROWS = 100


@dataclass
class Bundle:
    dir: Path
    meta: dict[str, Any]
    parity_max_abs: float | None = None
    files: dict[str, Path] = field(default_factory=dict)

    @property
    def feature_names(self) -> list[str]:
        return list(self.meta["feature_names"])

    @property
    def spec(self) -> FeatureSpec:
        return FeatureSpec.from_dict(self.meta["feature_spec"])

    @property
    def onnx_path(self) -> Path:
        return self.dir / MODEL_ONNX

    @property
    def booster_path(self) -> Path:
        return self.dir / BOOSTER_TXT

    @property
    def anomaly_path(self) -> Path | None:
        path = self.dir / ANOMALY_ONNX
        return path if path.exists() else None


def isotonic_maps(raw: np.ndarray, calibrated: np.ndarray) -> list[dict[str, list[float]]]:
    """Per-class monotone maps raw probability -> calibrated probability, as interpolation knots.

    Fitted on the training rows' raw (base model) and calibrated (CalibratedClassifierCV) outputs,
    so the edge reproduces the server's calibration without shipping the three fold calibrators.
    """
    from sklearn.isotonic import IsotonicRegression

    raw = np.atleast_2d(raw)
    calibrated = np.atleast_2d(calibrated)
    maps = []
    for k in range(raw.shape[1]):
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(raw[:, k], calibrated[:, k])
        maps.append({"x": iso.X_thresholds_.tolist(), "y": iso.y_thresholds_.tolist()})
    return maps


def apply_isotonic(raw: np.ndarray, maps: list[dict[str, list[float]]]) -> np.ndarray:
    """Calibrate (n, k) raw probabilities with `isotonic_maps` knots; rows renormalised to sum to 1."""
    raw = np.atleast_2d(raw)
    out = np.column_stack([np.interp(raw[:, k], m["x"], m["y"]) for k, m in enumerate(maps)])
    totals = out.sum(axis=1, keepdims=True)
    return np.where(totals > 0, out / np.where(totals > 0, totals, 1.0), raw)


def save_bundle(
    directory: Path | str,
    *,
    model: Any,
    task: str,
    feature_names: list[str],
    spec: FeatureSpec,
    background: np.ndarray,
    parity_X: np.ndarray | None = None,
    conformal_q: float | None = None,
    coverage: float | None = None,
    isotonic: list[dict[str, list[float]]] | None = None,
    classes: list[str] | None = None,
    anomaly: Any | None = None,
    rul_cap: float | None = None,
    extra: dict[str, Any] | None = None,
    export_onnx: bool = True,
) -> Bundle:
    """Write every bundle file for a fitted LightGBM ``model``; returns the bundle with its ONNX parity.

    Thresholds are snapped to float32 before anything is written, so model.pkl, booster.txt and
    model.onnx are the same model; parity is measured on ``parity_X`` (default: the background rows).
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}

    parity_max_abs: float | None = None
    if export_onnx:
        from twinvoice_pdm.registry.onnx_export import export_lgbm, parity, snap_thresholds

        snap_thresholds(model)
        files["onnx"] = export_lgbm(model, len(feature_names), directory / MODEL_ONNX)
        check_X = parity_X if parity_X is not None else background
        parity_max_abs = parity(model, files["onnx"], np.asarray(check_X)).max_abs

    anomaly_meta: dict[str, Any] = {}
    if anomaly is not None:
        # An `AnomalyDetector`: its forest scores the same feature vector the regressor sees.
        anomaly_meta = {
            "anomaly_baseline_q95": float(anomaly._baseline_q95),
            "anomaly_offset": float(anomaly.model.offset_),
        }
        if export_onnx:
            from twinvoice_pdm.registry.onnx_export import export_isolation_forest

            files["anomaly"] = export_isolation_forest(anomaly.model, len(feature_names), directory / ANOMALY_ONNX)

    background = np.asarray(background, dtype=float)[:BACKGROUND_ROWS]
    files["pkl"] = directory / MODEL_PKL
    with files["pkl"].open("wb") as handle:
        pickle.dump({"model": model, "background": background, "anomaly": anomaly}, handle)

    files["booster"] = directory / BOOSTER_TXT
    model.booster_.save_model(str(files["booster"]))

    meta: dict[str, Any] = {
        "bundle_version": BUNDLE_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "task": task,
        "feature_names": list(feature_names),
        "feature_spec": spec.to_dict(),
        "conformal_q": conformal_q,
        "coverage": coverage,
        "isotonic": isotonic,
        "classes": classes,
        "anomaly_baseline_q95": None,
        "anomaly_offset": None,
        **anomaly_meta,
        "rul_cap": rul_cap,
        "onnx_parity_max_abs": parity_max_abs,
        **(extra or {}),
    }
    files["json"] = directory / BUNDLE_JSON
    files["json"].write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return Bundle(dir=directory, meta=meta, parity_max_abs=parity_max_abs, files=files)


def load_bundle(directory: Path | str) -> Bundle:
    """Read bundle.json (not the pickle: the edge must never unpickle anything)."""
    directory = Path(directory)
    meta = json.loads((directory / BUNDLE_JSON).read_text(encoding="utf-8"))
    names = (("onnx", MODEL_ONNX), ("booster", BOOSTER_TXT), ("pkl", MODEL_PKL), ("anomaly", ANOMALY_ONNX))
    files = {k: directory / name for k, name in names if (directory / name).exists()}
    return Bundle(dir=directory, meta=meta, parity_max_abs=meta.get("onnx_parity_max_abs"), files=files)


def load_model_pickle(directory: Path | str) -> dict[str, Any]:
    """The {"model", "background"} artifact, for trusted server-side code only."""
    with (Path(directory) / MODEL_PKL).open("rb") as handle:
        return pickle.load(handle)
