"""ONNX Runtime inference for one model bundle: RUL + conformal interval, calibrated failure
probabilities, and the IsolationForest health index — everything from bundle.json, nothing pickled."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from twinvoice_pdm.anomaly import normalise_anomaly
from twinvoice_pdm.registry.bundle import Bundle, apply_isotonic, load_bundle
from twinvoice_pdm.registry.onnx_export import onnx_anomaly_raw, onnx_predict, onnx_session


@dataclass
class Inference:
    rul: dict[str, Any] | None = None
    failure_probability: dict[str, float] | None = None
    health_index: float | None = None
    anomaly_score: float | None = None
    confidence: str | None = None
    reasons: list[str] = field(default_factory=list)
    infer_ms: float = 0.0


def latest_bundle_dir(model_dir: Path | str, model_name: str) -> Path:
    """`{model_dir}/{name}/{version}/`, newest version (versions are sortable timestamps)."""
    root = Path(model_dir) / model_name
    versions = sorted(p for p in root.iterdir() if (p / "bundle.json").exists()) if root.exists() else []
    if not versions:
        raise FileNotFoundError(f"no bundle for model {model_name!r} under {model_dir}; run `make train`")
    return versions[-1]


class EdgeModel:
    def __init__(self, bundle_dir: Path | str) -> None:
        self.bundle: Bundle = load_bundle(bundle_dir)
        self.meta = self.bundle.meta
        self.session = onnx_session(self.bundle.onnx_path)
        anomaly = self.bundle.anomaly_path
        self.anomaly_session = onnx_session(anomaly) if anomaly is not None else None
        self.name = str(self.meta.get("name") or Path(bundle_dir).parent.name)
        self.version = Path(bundle_dir).name

    @property
    def model_version(self) -> str:
        """What ingest resolves back to a `models` row."""
        return f"{self.name}:{self.version}"

    @property
    def feature_names(self) -> list[str]:
        return self.bundle.feature_names

    def predict(self, x: np.ndarray) -> Inference:
        started = time.perf_counter()
        X = np.asarray(x, dtype=np.float64).reshape(1, -1)
        out = Inference()
        raw = onnx_predict(self.session, X)

        if self.meta["task"] == "rul":
            cap = float(self.meta.get("rul_cap") or np.inf)
            point = float(np.clip(raw[0], 0, cap))
            q = float(self.meta.get("conformal_q") or 0.2 * point)
            out.rul = {
                "point": point,
                "low": float(np.clip(point - q, 0, cap)),
                "high": float(np.clip(point + q, 0, cap)),
                "unit": self.meta.get("rul_unit") or "cycles",
                "coverage": self.meta.get("coverage"),
            }
            out.confidence, out.reasons = _confidence(2 * q, cap)
        else:
            probabilities = np.atleast_2d(raw)
            if self.meta.get("isotonic"):
                probabilities = apply_isotonic(probabilities, self.meta["isotonic"])
            classes = self.meta.get("classes") or [str(i) for i in range(probabilities.shape[1])]
            out.failure_probability = {str(c): float(p) for c, p in zip(classes, probabilities[0], strict=True)}

        if self.anomaly_session is not None:
            raw_score = float(onnx_anomaly_raw(self.anomaly_session, X, float(self.meta["anomaly_offset"]))[0])
            q95 = float(self.meta.get("anomaly_baseline_q95") or 1.0)
            out.anomaly_score = float(normalise_anomaly(np.array([raw_score]), q95)[0])
            out.health_index = round(100.0 * (1.0 - out.anomaly_score), 2)

        out.infer_ms = (time.perf_counter() - started) * 1000
        return out


def _confidence(width: float, cap: float) -> tuple[str, list[str]]:
    """Interval width relative to the RUL range: a narrow interval is a confident one."""
    if not np.isfinite(cap) or cap <= 0:
        return "medium", []
    relative = width / cap
    if relative < 0.15:
        return "high", []
    if relative < 0.35:
        return "medium", []
    return "low", ["wide_interval"]
