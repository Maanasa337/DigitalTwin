"""Server-side scoring with trained bundles: the 30 s inference job, model insights, signature modes."""

import uuid
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.pdm import scoring
from app.modules.pdm.models import Model, Prediction
from app.modules.xai.models import ExplanationQualityMetric
from app.modules.xai.modes import signature_mode
from app.workers.tasks import infer, insights
from tests.conftest import auth

SENSORS = ["spindle.vib_rms", "motor.current", "speed_pct"]  # speed_pct has no sensor row: imputed
STATS = ["mean", "std", "slope", "last"]
WINDOW = 6


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    """A small real bundle: LightGBM RUL regressor plus the IsolationForest health model."""
    from lightgbm import LGBMRegressor
    from twinvoice_pdm.anomaly import AnomalyDetector
    from twinvoice_pdm.features import FeatureSpec, feature_names
    from twinvoice_pdm.registry.bundle import save_bundle

    spec = FeatureSpec(window_size=WINDOW, stride=1, stat_features=STATS, sensor_cols=SENSORS)
    names = feature_names(SENSORS, spec)
    rng = np.random.default_rng(0)
    X = rng.normal(size=(300, len(names))) + np.array([3.0, 0.2, 0.0, 3.0, 20.0, 1.0, 0.0, 20.0, 80.0, 1, 0, 80.0])
    y = np.clip(90 - 12 * (X[:, 0] - 3.0) - (X[:, 4] - 20.0), 0, 90)
    model = LGBMRegressor(n_estimators=30, verbose=-1).fit(X, y)
    save_bundle(
        tmp_path / "rul-test" / "v1",
        model=model,
        task="rul",
        feature_names=names,
        spec=spec,
        background=X[:50],
        conformal_q=4.0,
        coverage=0.9,
        rul_cap=90.0,
        anomaly=AnomalyDetector(n_estimators=20).fit(X),
        extra={"rul_unit": "d"},
        export_onnx=False,
    )
    return tmp_path / "rul-test" / "v1"


def _register(session: Session, bundle: Path, **overrides: Any) -> Model:
    values: dict[str, Any] = {
        "name": "rul-synthetic-cnc_mill",
        "version": uuid.uuid4().hex[:8],
        "task": "rul",
        "algorithm": "lightgbm",
        "asset_type": "cnc_mill",
        "dataset_ref": "synthetic:cnc_mill",
        "dataset_hash": "test",
        "feature_set": {},
        "artifact_uri": f"file://{(bundle / 'model.pkl').as_posix()}",
        "stage": "production",
        **overrides,
    }
    model = Model(**values)
    session.add(model)
    session.flush()
    return model


def _telemetry(session: Session, asset_id: str, end: datetime, seconds: int = 80) -> None:
    sensors = dict(
        session.execute(
            text("SELECT metric_name, id FROM sensors WHERE asset_id = :a"), {"a": uuid.UUID(asset_id)}
        ).all()
    )
    rows = []
    for i in range(0, seconds, 2):
        at = end - timedelta(seconds=seconds - i)
        rows.append({"time": at, "sensor_id": sensors["spindle.vib_rms"], "value": 3.0 + 0.01 * i})
        rows.append({"time": at, "sensor_id": sensors["motor.current"], "value": 20.0})
    session.execute(
        text("INSERT INTO telemetry (time, sensor_id, value, quality) VALUES (:time, :sensor_id, :value, 192)"), rows
    )
    session.flush()


@pytest.fixture
def quiet(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """No Celery, Ditto or Valkey in tests: record what would have been enqueued instead."""
    from app.workers.tasks import explain

    queued: list[str] = []
    monkeypatch.setattr(explain.explain_prediction, "delay", queued.append)
    monkeypatch.setattr(infer, "_publish", lambda code, properties: None)
    return queued


def test_the_job_scores_an_asset_with_its_type_model(
    session: Session, seeded_asset: dict[str, Any], bundle: Path, quiet: list[str]
) -> None:
    model = _register(session, bundle)
    now = datetime.now(UTC)
    _telemetry(session, seeded_asset["id"], infer._window_end(now))

    prediction_id = infer.infer_asset(lambda: nullcontext(session), uuid.UUID(seeded_asset["id"]), "cnc-01", "cnc_mill")

    assert prediction_id is not None and quiet == [str(prediction_id)]
    row = session.scalars(select(Prediction).where(Prediction.id == prediction_id)).one()
    assert row.model_id == model.id and row.source == "server"
    assert row.rul_unit == "d" and 0 <= row.rul_low <= row.rul_point <= row.rul_high <= 90  # type: ignore[operator]
    assert row.rul_high - row.rul_low == pytest.approx(8.0, abs=1e-6) or row.rul_low == 0  # type: ignore[operator]
    assert row.health_index is not None and 0 <= float(row.health_index) <= 100
    # The window sits on the 10 s grid, so the explainer can rebuild exactly these buckets.
    assert row.window_end.timestamp() % scoring.SAMPLE_PERIOD_S == 0
    assert row.window_end - row.window_start == timedelta(seconds=WINDOW * scoring.SAMPLE_PERIOD_S)
    assert "imputed_features" in row.confidence_reasons  # speed_pct is not stored as a sensor


def test_the_imputed_value_is_the_training_median(session: Session, seeded_asset: dict[str, Any], bundle: Path) -> None:
    loaded = scoring.load(_register(session, bundle))
    assert loaded is not None
    end = infer._window_end(datetime.now(UTC))
    _telemetry(session, seeded_asset["id"], end)

    window = scoring.telemetry_window(session, uuid.UUID(seeded_asset["id"]), loaded.spec, end)
    assert window is not None and window.missing == ["speed_pct"] and window.fill == 1.0
    x, imputed = scoring.feature_vector(loaded, window)

    assert imputed == [f"speed_pct_{s}" for s in STATS]
    index = loaded.feature_names.index("speed_pct_mean")
    assert x[index] == pytest.approx(float(np.median(loaded.background[:, index])))  # type: ignore[index]
    assert x[loaded.feature_names.index("motor.current_mean")] == pytest.approx(20.0)


def test_a_fresh_edge_prediction_keeps_the_server_off_that_asset(
    session: Session, seeded_asset: dict[str, Any], bundle: Path, quiet: list[str]
) -> None:
    model = _register(session, bundle)
    now = datetime.now(UTC)
    _telemetry(session, seeded_asset["id"], infer._window_end(now))
    session.add(
        Prediction(
            time=now - timedelta(seconds=30),
            asset_id=uuid.UUID(seeded_asset["id"]),
            model_id=model.id,
            window_start=now - timedelta(minutes=1),
            window_end=now,
            source="edge",
        )
    )
    session.flush()

    assert infer.infer_asset(lambda: nullcontext(session), uuid.UUID(seeded_asset["id"]), "cnc-01", "cnc_mill") is None
    assert quiet == []


def test_a_silent_asset_is_not_scored(session: Session, seeded_asset: dict[str, Any], bundle: Path) -> None:
    loaded = scoring.load(_register(session, bundle))
    end = infer._window_end(datetime.now(UTC))
    _telemetry(session, seeded_asset["id"], end, seconds=20)  # 2 of 6 buckets

    assert scoring.telemetry_window(session, uuid.UUID(seeded_asset["id"]), loaded.spec, end) is None  # type: ignore[union-attr]


def test_model_selection_prefers_the_asset_model_and_skips_benchmark_models(
    session: Session, seeded_asset: dict[str, Any], bundle: Path
) -> None:
    asset_id = uuid.UUID(seeded_asset["id"])
    _register(session, bundle, name="rul-cmapss-fd001", asset_type=None, dataset_ref="cmapss:FD001")
    assert scoring.select_model(session, asset_id, "cnc_mill") is None

    by_type = _register(session, bundle)
    assert scoring.select_model(session, asset_id, "cnc_mill") == by_type
    assert scoring.select_model(session, asset_id, "compressor") is None

    bound = _register(session, bundle, name="rul-cnc-01", asset_id=asset_id)
    assert scoring.select_model(session, asset_id, "cnc_mill") == bound


def test_a_model_without_a_bundle_is_skipped(session: Session, tmp_path: Path) -> None:
    model = _register(session, tmp_path / "gone")
    assert scoring.load(model) is None


def test_insights_write_importance_pdp_and_quality_metrics(session: Session, bundle: Path) -> None:
    model = _register(session, bundle)

    assert insights.compute(session, model.id) is True

    session.refresh(model)
    importance = model.hyperparams["global_importance"]
    assert set(importance) == set(scoring.load(model).feature_names)  # type: ignore[union-attr]
    # y was built from vib_rms and current means, so those lead.
    assert max(importance, key=importance.get) in {"spindle.vib_rms_mean", "spindle.vib_rms_last"}
    assert len(model.hyperparams["partial_dependence"]) == insights.PDP_FEATURES
    metrics = {
        m.metric: m.value
        for m in session.scalars(select(ExplanationQualityMetric).where(ExplanationQualityMetric.model_id == model.id))
    }
    assert set(metrics) == {"deletion_auc", "insertion_auc", "pgi", "sparsity", "sensitivity_max"}
    assert all(np.isfinite(v) for v in metrics.values())

    # A recompute replaces the rows instead of piling up history.
    insights.compute(session, model.id)
    count = session.scalar(
        select(text("count(*)"))
        .select_from(ExplanationQualityMetric)
        .where(ExplanationQualityMetric.model_id == model.id)
    )
    assert count == len(metrics)


def test_quality_endpoint_reports_llm_state_and_refresh_is_engineer_only(
    client: TestClient, session: Session, bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = _register(session, bundle)
    queued: list[str] = []
    monkeypatch.setattr(insights.compute_model_insights, "delay", queued.append)

    body = client.get(f"/api/v1/models/{model.id}/quality-metrics", headers=auth("engineer")).json()
    assert body["llm_enabled"] is False and body["metrics"] == []

    url = f"/api/v1/models/{model.id}/quality-metrics/refresh"
    assert client.post(url, headers=auth("engineer")).status_code == 202
    assert queued == [str(model.id)]
    assert (
        client.post(f"/api/v1/models/{uuid.uuid4()}/quality-metrics/refresh", headers=auth("admin")).status_code == 404
    )
    # Last: a rejected request rolls the test session back, taking the model row with it.
    assert client.post(url, headers=auth("technician")).status_code == 403


def test_training_without_a_task_queue_is_a_503_not_a_fake_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.workers.tasks import train

    def down(**_: Any) -> None:
        raise ConnectionError("broker down")

    monkeypatch.setattr(train.train_model_task, "delay", down)
    response = client.post("/api/v1/models/train", json={"asset_type": "cnc_mill"}, headers=auth("engineer"))
    assert response.status_code == 503


def test_signature_mode_names_the_mode_the_evidence_supports(session: Session, seeded_asset: dict[str, Any]) -> None:
    from twinvoice_xai.attribution import build_attributions

    session.execute(
        text(
            "INSERT INTO failure_modes (id, asset_type, code, name, signature, severity) VALUES "
            "(gen_random_uuid(), 'cnc_mill', 'bearing_wear', 'Bearing', '{\"metrics\": [\"spindle.vib_rms\"]}', 3), "
            "(gen_random_uuid(), 'cnc_mill', 'tool_wear', 'Tool', '{\"metrics\": [\"tool.wear\"]}', 3) "
            "ON CONFLICT DO NOTHING"
        )
    )
    attributions = build_attributions(
        ["spindle.vib_rms_mean", "tool.wear_last", "power_kw_mean"], np.ones(3), np.array([-5.0, -1.0, 0.5])
    )
    asset_id = uuid.UUID(seeded_asset["id"])

    assert signature_mode(session, asset_id, attributions, health_index=40.0) == "bearing_wear"
    assert signature_mode(session, asset_id, attributions, health_index=95.0) == "normal"


def test_a_long_prediction_range_is_thinned_evenly_not_truncated(
    session: Session, seeded_asset: dict[str, Any], bundle: Path
) -> None:
    from app.modules.pdm.repository import PredictionRepository

    model = _register(session, bundle)
    asset_id = uuid.UUID(seeded_asset["id"])
    start = datetime(2026, 1, 1, tzinfo=UTC)
    session.add_all(
        Prediction(
            time=start + timedelta(minutes=i),
            asset_id=asset_id,
            model_id=model.id,
            window_start=start,
            window_end=start,
            source="edge",
        )
        for i in range(250)
    )
    session.flush()

    rows = PredictionRepository(session).query(asset_id, start, start + timedelta(days=1), limit=100)

    assert len(rows) == 84  # every 3rd of 250
    assert rows[0].time == start and rows[-1].time == start + timedelta(minutes=249)
    assert [r.time for r in rows] == sorted(r.time for r in rows)
