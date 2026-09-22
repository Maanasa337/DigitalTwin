"""Celery task: on-demand model training (FR-PM-04), with ONNX export (FR-EDGE-01).

``dataset_ref`` selects the data:

  cmapss:FD00x          RUL on a C-MAPSS subset (data/raw), scored on the official test engines
  ai4i                  failure classification on AI4I 2020, stratified hold-out
  synthetic:{type}      RUL on the simulator's Parquet exports (data/synthetic) for one asset type;
                        features are named after the live Sparkplug metrics (`spindle.vib_rms_mean`),
                        so the bundle can score the MQTT stream on an edge runner as-is

Each run fits the model, evaluates it on data held out by unit (engine / asset), writes the bundle
(`twinvoice_pdm.registry.bundle`) under ``{models_dir}/{name}/{version}/``, records the ONNX parity
as the ``onnx_parity_max_abs`` metric, and registers a candidate model.

``python -m app.workers.tasks.train --bootstrap`` trains one synthetic RUL model per asset type plus
``cmapss:FD001`` and promotes them (``make train``).
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)

# Counters and ground truth are in the export but are not sensor readings a model may see.
SYNTHETIC_NON_FEATURES = frozenset(
    {"energy_kwh", "good_count", "reject_count", "ram.cycle_count", "damage", "true_rul_h"}
)
SYNTHETIC_STATS = ["mean", "std", "slope", "last"]
# Simulator RUL runs to ~2000 h. It is modelled in days: the C-MAPSS 125-cycle cap would flatten
# hours, and float32 ONNX sums cannot hold values in the thousands to the 1e-4 parity tolerance.
SYNTHETIC_RUL_CAP = 90.0
SYNTHETIC_RUL_UNIT = "d"
SYNTHETIC_MIN_ROWS = 500
ASSET_TYPES = ("cnc_mill", "compressor", "conveyor", "hydraulic_press", "injection_moulder")


@dataclass
class TrainOutcome:
    """Everything `register_model` needs, produced by one of the dataset-specific trainers."""

    name: str
    task: str
    dataset_ref: str
    dataset_hash: str
    feature_names: list[str]
    bundle: Any
    metrics: dict[str, float]
    asset_type: str | None = None
    window_size: int | None = None
    stride: int | None = None
    rul_unit: str | None = None
    hyperparams: dict[str, Any] = field(default_factory=dict)


@celery_app.task(name="app.workers.tasks.train.train_model_task", bind=True)
def train_model_task(
    self: Any,
    *,
    task: str = "rul",
    algorithm: str = "lightgbm",
    asset_type: str | None = None,
    asset_id: str | None = None,
    dataset_ref: str | None = None,
    window_size: int = 60,
    stride: int = 10,
    horizon: int = 30,
    hyperparams: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Train a model and register it. Returns model ID and key metrics."""
    ref = dataset_ref or (f"synthetic:{asset_type}" if asset_type else "cmapss:FD001")
    log.info("training %s model on %s", task, ref)
    model_id, outcome, version = train_and_register(
        task=task,
        dataset_ref=ref,
        algorithm=algorithm,
        asset_id=uuid.UUID(asset_id) if asset_id else None,
        window_size=window_size,
        stride=stride,
        horizon=horizon,
        hyperparams=hyperparams or {},
    )
    return {"model_id": str(model_id), "name": outcome.name, "version": version, "metrics": outcome.metrics}


def train_and_register(
    *,
    task: str,
    dataset_ref: str,
    algorithm: str = "lightgbm",
    asset_id: uuid.UUID | None = None,
    window_size: int = 60,
    stride: int = 10,
    horizon: int | None = None,
    hyperparams: dict[str, Any] | None = None,
    promote: bool = False,
) -> tuple[uuid.UUID, TrainOutcome, str]:
    from app.core.config import get_settings
    from app.core.db import get_sessionmaker
    from app.modules.pdm.service import ModelService

    if algorithm != "lightgbm":
        raise ValueError(f"algorithm {algorithm!r} is not supported; only lightgbm exports to ONNX here")
    settings = get_settings()
    version = datetime.now(UTC).strftime("%Y.%m.%d-%H%M%S")
    hyperparams = hyperparams or {}
    kind, _, arg = dataset_ref.partition(":")

    def bundle_dir(name: str) -> Path:
        return Path(settings.models_dir) / name / version

    if kind == "cmapss" and task == "rul":
        outcome = _train_cmapss(arg or "FD001", settings.raw_data_dir, bundle_dir, hyperparams)
    elif kind == "ai4i" and task == "failure":
        outcome = _train_ai4i(settings.raw_data_dir, bundle_dir, hyperparams)
    elif kind == "synthetic" and task == "rul":
        outcome = _train_synthetic(arg, settings.synthetic_dir, bundle_dir, window_size, stride, hyperparams)
    else:
        raise ValueError(
            f"cannot train task {task!r} on {dataset_ref!r}; supported: rul on cmapss:FD00x or "
            "synthetic:{asset_type}, failure on ai4i"
        )

    files = outcome.bundle.files
    parity = outcome.bundle.parity_max_abs
    metrics = [{"split": "test", "metric": k, "value": float(v)} for k, v in outcome.metrics.items()]
    if parity is not None:
        metrics.append({"split": "test", "metric": "onnx_parity_max_abs", "value": float(parity)})

    with get_sessionmaker()() as session:
        service = ModelService(session)
        model = service.register_model(
            actor=None,
            name=outcome.name,
            version=version,
            task=outcome.task,
            algorithm=algorithm,
            asset_type=outcome.asset_type,
            asset_id=asset_id,
            dataset_ref=outcome.dataset_ref,
            dataset_hash=outcome.dataset_hash,
            feature_set={
                "features": outcome.feature_names,
                "spec": outcome.bundle.meta["feature_spec"],
                "rul_unit": outcome.rul_unit,
            },
            artifact_uri=_uri(files["pkl"]),
            hyperparams={**outcome.hyperparams, **hyperparams},
            window_size=outcome.window_size,
            stride=outcome.stride,
            horizon=horizon,
            onnx_uri=_uri(files["onnx"]) if "onnx" in files else None,
            conformal_uri=_uri(files["json"]) if outcome.task == "rul" else None,
            calibrator_uri=_uri(files["json"]) if outcome.task == "failure" else None,
            explainer_uri=_uri(files["booster"]),
            metrics=metrics,
        )
        if promote:
            service.promote(None, model.id)  # type: ignore[arg-type]
        model_id = model.id
        # Importance and explanation quality come from the bundle just written; a failure here must
        # not lose the trained model, which is already registered.
        try:
            from app.workers.tasks.insights import compute

            compute(session, model_id)
        except Exception:
            log.exception("insights failed for %s v%s", outcome.name, version)
    log.info("trained %s v%s (id=%s): %s", outcome.name, version, model_id, outcome.metrics)
    return model_id, outcome, version


def _uri(path: Path) -> str:
    return f"file://{Path(path).resolve().as_posix()}"


# ── Dataset-specific trainers ─────────────────────────────────────────


def _rul_metrics(estimator: Any, X: np.ndarray, y: np.ndarray, cap: float) -> dict[str, float]:
    prediction = estimator.predict(X)
    truth = np.clip(y, 0, cap)
    point, low, high = prediction["point"], prediction["low"], prediction["high"]
    return {
        "rmse": float(np.sqrt(np.mean((point - truth) ** 2))),
        "coverage_90": float(np.mean((low <= truth) & (truth <= high))),
        "interval_width": float(np.mean(high - low)),
    }


def _train_cmapss(subset: str, raw_dir: str, bundle_dir: Any, hyperparams: dict[str, Any]) -> TrainOutcome:
    from twinvoice_pdm.benchmark import cmapss
    from twinvoice_pdm.datasets import dataset_sha
    from twinvoice_pdm.features import FeatureSpec
    from twinvoice_pdm.registry.bundle import save_bundle
    from twinvoice_pdm.rul import RUL_CAP, RulEstimator

    subset = subset.upper()
    if subset not in cmapss.SUBSETS:
        raise ValueError(f"unknown C-MAPSS subset {subset}")
    data = cmapss.prepare(raw_dir, subset)
    x_train, y_train, groups = data["x_train"], data["y_train"], data["groups"]
    names = list(x_train.columns)

    estimator = RulEstimator(n_estimators=int(hyperparams.get("n_estimators", 700)), learning_rate=0.02)
    estimator.base_model.set_params(min_child_samples=40, subsample=0.8, subsample_freq=1, colsample_bytree=0.7)
    estimator.fit(x_train.to_numpy(), y_train, conformal=True, groups=groups)
    q = estimator.residual_quantile(x_train.to_numpy(), y_train, groups)
    x_test = data["x_test"].to_numpy()
    metrics = _rul_metrics(estimator, x_test, data["y_test"], RUL_CAP)
    metrics["nasa_score"] = cmapss.nasa_score(np.clip(data["y_test"], 0, RUL_CAP), estimator.predict(x_test)["point"])

    name = f"rul-cmapss-{subset.lower()}"
    spec = FeatureSpec(window_size=cmapss.WINDOW, stride=1, stat_features=cmapss.STATS, sensor_cols=data["sensors"])
    bundle = save_bundle(
        bundle_dir(name),
        model=estimator.base_model,
        task="rul",
        feature_names=names,
        spec=spec,
        background=x_train.sample(min(100, len(x_train)), random_state=42).to_numpy(),
        parity_X=x_test,
        conformal_q=q,
        coverage=estimator.coverage,
        rul_cap=RUL_CAP,
        extra={"rul_unit": "cycles", "name": name, "dataset_ref": f"cmapss:{subset}"},
    )
    return TrainOutcome(
        name=name,
        task="rul",
        dataset_ref=f"cmapss:{subset}",
        dataset_hash=(dataset_sha(raw_dir, "cmapss") or "unknown")[:16],
        feature_names=names,
        bundle=bundle,
        metrics=metrics,
        window_size=cmapss.WINDOW,
        stride=1,
        rul_unit="cycles",
        hyperparams={"rul_cap": RUL_CAP, "conformal_q": q},
    )


def _train_ai4i(raw_dir: str, bundle_dir: Any, hyperparams: dict[str, Any]) -> TrainOutcome:
    from sklearn.metrics import f1_score, roc_auc_score
    from sklearn.model_selection import train_test_split
    from twinvoice_pdm.benchmark.ai4i import expected_calibration_error
    from twinvoice_pdm.datasets import AI4I_TARGET, dataset_sha, load_ai4i
    from twinvoice_pdm.failure import FailureClassifier
    from twinvoice_pdm.features import FeatureSpec
    from twinvoice_pdm.registry.bundle import isotonic_maps, save_bundle

    df = load_ai4i(Path(raw_dir) / "ai4i")
    labels = np.where(df.pop(AI4I_TARGET).to_numpy() == 1, "failure", "none")
    names = list(df.columns)
    x_train, x_test, y_train, y_test = train_test_split(
        df.to_numpy(dtype=float), labels, test_size=0.2, stratify=labels, random_state=42
    )
    classifier = FailureClassifier(n_estimators=int(hyperparams.get("n_estimators", 400)))
    classifier.base_model.set_params(class_weight="balanced", num_leaves=15, min_child_samples=10)
    classifier.fit(x_train, y_train, calibrate=True)

    proba = classifier.predict_proba(x_test)
    positive = list(classifier.classes_).index("failure")
    truth = (y_test == "failure").astype(int)
    metrics = {
        "auc": float(roc_auc_score(truth, proba[:, positive])),
        "f1": float(f1_score(truth, (proba[:, positive] >= 0.5).astype(int), zero_division=0)),
        "ece": expected_calibration_error(truth, proba[:, positive]),
    }
    isotonic = isotonic_maps(classifier.base_model.predict_proba(x_train), classifier.predict_proba(x_train))

    name = "failure-ai4i"
    bundle = save_bundle(
        bundle_dir(name),
        model=classifier.base_model,
        task="failure",
        feature_names=names,
        # Rows are single readings, not windows: a one-sample "window" of the raw columns.
        spec=FeatureSpec(window_size=1, stride=1, stat_features=["last"], sensor_cols=names),
        background=x_train[:100],
        parity_X=x_test,
        isotonic=isotonic,
        classes=[str(c) for c in classifier.classes_],
        extra={"name": name, "dataset_ref": "ai4i"},
    )
    return TrainOutcome(
        name=name,
        task="failure",
        dataset_ref="ai4i",
        dataset_hash=(dataset_sha(raw_dir, "ai4i") or "unknown")[:16],
        feature_names=names,
        bundle=bundle,
        metrics=metrics,
    )


def synthetic_frame(synthetic_dir: str, asset_type: str) -> tuple[Any, list[str]]:
    """The export rows for one asset type and the metric columns that type actually publishes."""
    from twinvoice_pdm.datasets import load_synthetic

    df = load_synthetic(synthetic_dir)
    df = df[df["asset_type"] == asset_type]
    if len(df) < SYNTHETIC_MIN_ROWS:
        raise ValueError(f"only {len(df)} exported rows for asset type {asset_type!r} in {synthetic_dir}")
    if "state" in df.columns:
        df = df[df["state"] == "RUNNING"]
    df = df[df["true_rul_h"].notna()].sort_values(["asset_code", "time"]).reset_index(drop=True)
    metrics = [
        c
        for c in df.columns
        if c not in SYNTHETIC_NON_FEATURES
        and not c.startswith("damage.")
        and c not in ("time", "asset_code", "asset_type", "state", "driver", "failure_mode")
        and np.issubdtype(df[c].dtype, np.number)
        and df[c].notna().mean() > 0.9
    ]
    df[metrics] = df.groupby("asset_code")[metrics].ffill().fillna(0.0)
    return df, metrics


def _train_synthetic(
    asset_type: str, synthetic_dir: str, bundle_dir: Any, window: int, stride: int, hyperparams: dict[str, Any]
) -> TrainOutcome:
    from twinvoice_pdm.anomaly import AnomalyDetector
    from twinvoice_pdm.datasets import frame_hash
    from twinvoice_pdm.features import FeatureSpec, build_features
    from twinvoice_pdm.registry.bundle import save_bundle
    from twinvoice_pdm.rul import RulEstimator

    if asset_type not in ASSET_TYPES:
        raise ValueError(f"unknown asset type {asset_type!r}; known: {', '.join(ASSET_TYPES)}")
    df, metrics_cols = synthetic_frame(synthetic_dir, asset_type)
    spec = FeatureSpec(window_size=window, stride=stride, stat_features=SYNTHETIC_STATS, sensor_cols=metrics_cols)
    features = build_features(df, spec, group_col="asset_code")
    if features.empty:
        raise ValueError(f"no complete {window}-sample window for asset type {asset_type!r}")
    ends = df.loc[features.index]
    X, groups = features.to_numpy(), ends["asset_code"].to_numpy()
    y = ends["true_rul_h"].to_numpy(dtype=float) / 24.0
    names = list(features.columns)

    # Held out by asset when the type has more than one; a single press is split by time instead.
    assets = sorted(set(groups))
    test_mask = groups == assets[-1] if len(assets) > 1 else np.arange(len(y)) >= int(len(y) * 0.8)

    estimator = RulEstimator(
        n_estimators=int(hyperparams.get("n_estimators", 300)), learning_rate=0.05, cap=SYNTHETIC_RUL_CAP
    )
    train_groups = groups[~test_mask] if len(assets) > 2 else None
    estimator.fit(X[~test_mask], y[~test_mask], conformal=True, groups=train_groups)
    metrics = _rul_metrics(estimator, X[test_mask], y[test_mask], SYNTHETIC_RUL_CAP)
    parity_X = X[test_mask]

    # The metrics above are the honest held-out numbers. The shipped model then learns from every
    # asset: it will score these same machines live, and two or three assets per type is too few
    # to leave one out of the model the edge actually runs.
    all_groups = groups if len(assets) > 1 else None
    estimator.fit(X, y, conformal=False)
    q = estimator.residual_quantile(X, y, all_groups)

    # Health index: the forest learns the least-damaged half of the windows as "normal".
    damage = ends["damage"].to_numpy(dtype=float)
    healthy = X[damage <= np.quantile(damage, 0.5)]
    anomaly = AnomalyDetector(n_estimators=100).fit(healthy)

    name = f"rul-synthetic-{asset_type}"
    bundle = save_bundle(
        bundle_dir(name),
        model=estimator.base_model,
        task="rul",
        feature_names=names,
        spec=spec,
        background=X[:: max(1, len(X) // 100)],
        parity_X=parity_X,
        conformal_q=q,
        coverage=estimator.coverage,
        rul_cap=SYNTHETIC_RUL_CAP,
        anomaly=anomaly,
        extra={
            "rul_unit": SYNTHETIC_RUL_UNIT,
            "asset_type": asset_type,
            "name": name,
            "dataset_ref": f"synthetic:{asset_type}",
        },
    )
    return TrainOutcome(
        name=name,
        task="rul",
        dataset_ref=f"synthetic:{asset_type}",
        dataset_hash=frame_hash(df[metrics_cols]),
        feature_names=names,
        bundle=bundle,
        metrics=metrics,
        asset_type=asset_type,
        window_size=window,
        stride=stride,
        rul_unit=SYNTHETIC_RUL_UNIT,
        hyperparams={"rul_cap": SYNTHETIC_RUL_CAP, "conformal_q": q},
    )


# ── Bootstrap CLI ─────────────────────────────────────────────────────


def ensure_synthetic_export(synthetic_dir: str, hours: float = 72.0) -> None:
    """Ask the simulator for an export when there is none yet; the simulator writes the Parquet."""
    import httpx

    from app.core.config import get_settings

    if any(Path(synthetic_dir).glob("*.parquet")):
        return
    for base in dict.fromkeys([get_settings().simulator_url, "http://simulator:8090"]):
        try:
            log.info("no synthetic export in %s; requesting %s h from %s", synthetic_dir, hours, base)
            response = httpx.post(f"{base}/export", json={"hours": hours}, timeout=600)
            response.raise_for_status()
            return
        except httpx.HTTPError as exc:
            log.warning("simulator export via %s failed: %s", base, exc)
    raise RuntimeError("no synthetic export and the simulator could not produce one")


def bootstrap(asset_types: tuple[str, ...] = ASSET_TYPES, cmapss_subset: str | None = "FD001") -> int:
    """Train and promote the models a fresh install needs; returns how many failed."""
    from app.core.config import get_settings

    settings = get_settings()
    failures = 0
    jobs: list[dict[str, Any]] = []
    try:
        ensure_synthetic_export(settings.synthetic_dir)
        jobs += [{"task": "rul", "dataset_ref": f"synthetic:{t}"} for t in asset_types]
    except RuntimeError as exc:
        log.error("%s; skipping synthetic models", exc)
        failures += 1
    if cmapss_subset:
        jobs.append({"task": "rul", "dataset_ref": f"cmapss:{cmapss_subset}"})

    for job in jobs:
        try:
            model_id, outcome, version = train_and_register(**job, promote=True)
            print(f"{outcome.name} v{version} promoted ({model_id}): {outcome.metrics}")
        except Exception:
            log.exception("bootstrap training failed for %s", job["dataset_ref"])
            failures += 1
    return failures


def main(argv: list[str] | None = None) -> int:
    from app.core.observability import configure_logging

    parser = argparse.ArgumentParser(prog="python -m app.workers.tasks.train", description=__doc__)
    parser.add_argument("--bootstrap", action="store_true", help="train and promote the default model set")
    parser.add_argument("--task", default="rul", choices=["rul", "failure"])
    parser.add_argument("--dataset", default=None, help="cmapss:FD00x | ai4i | synthetic:{asset_type}")
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args(argv)
    configure_logging("INFO")

    if args.bootstrap:
        return 1 if bootstrap() else 0
    if not args.dataset:
        parser.error("--dataset is required without --bootstrap")
    model_id, outcome, version = train_and_register(task=args.task, dataset_ref=args.dataset, promote=args.promote)
    print(f"{outcome.name} v{version} ({model_id}): {outcome.metrics}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
