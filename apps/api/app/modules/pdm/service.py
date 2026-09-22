"""Service layer for predictive maintenance models and predictions (M5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.core.audit import snapshot, write_audit
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.core.security import CurrentUser
from app.modules.pdm.models import BenchmarkRun, Model, ModelMetric, Prediction
from app.modules.pdm.repository import (
    BenchmarkRepository,
    ModelMetricRepository,
    ModelRepository,
    PredictionRepository,
)
from app.modules.pdm.schemas import BenchmarkRunRequest, JobOut, PredictionOut


class ModelService:
    entity = "models"

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ModelRepository(session)
        self.metrics_repo = ModelMetricRepository(session)

    def list_models(
        self, params: PageParams, task: str | None = None, stage: str | None = None
    ) -> tuple[list[Model], int]:
        return self.repo.list_with_metrics(params, task, stage)

    def get_or_404(self, model_id: uuid.UUID) -> Model:
        obj = self.repo.get(model_id)
        if obj is None:
            raise NotFoundError(f"Model {model_id} not found")
        return obj

    def get_metrics(self, model_id: uuid.UUID) -> list[ModelMetric]:
        self.get_or_404(model_id)
        return self.metrics_repo.for_model(model_id)

    def promote(self, actor: CurrentUser, model_id: uuid.UUID) -> Model:
        model = self.get_or_404(model_id)
        if model.stage == "production":
            raise ConflictError("Model is already in production")
        before = snapshot(model)
        self.repo.promote(model)
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=model.id,
            action="promote",
            before=before,
            after=snapshot(model),
        )
        self.session.commit()
        return model

    def register_model(
        self,
        actor: CurrentUser | None,
        *,
        name: str,
        version: str,
        task: str,
        algorithm: str,
        dataset_ref: str,
        dataset_hash: str,
        feature_set: list[str] | dict[str, Any],
        artifact_uri: str,
        asset_type: str | None = None,
        asset_id: uuid.UUID | None = None,
        hyperparams: dict[str, Any] | None = None,
        window_size: int | None = None,
        stride: int | None = None,
        horizon: int | None = None,
        onnx_uri: str | None = None,
        conformal_uri: str | None = None,
        explainer_uri: str | None = None,
        calibrator_uri: str | None = None,
        metrics: list[dict[str, Any]] | None = None,
    ) -> Model:
        existing = self.repo.get_by_name_version(name, version)
        if existing:
            raise ConflictError(f"Model {name} v{version} already exists")

        model = Model(
            name=name,
            version=version,
            task=task,
            algorithm=algorithm,
            asset_type=asset_type,
            asset_id=asset_id,
            dataset_ref=dataset_ref,
            dataset_hash=dataset_hash,
            feature_set=feature_set,
            hyperparams=hyperparams or {},
            window_size=window_size,
            stride=stride,
            horizon=horizon,
            artifact_uri=artifact_uri,
            onnx_uri=onnx_uri,
            conformal_uri=conformal_uri,
            explainer_uri=explainer_uri,
            calibrator_uri=calibrator_uri,
        )
        self.repo.create(model)

        if metrics:
            metric_objs = [
                ModelMetric(model_id=model.id, split=m["split"], metric=m["metric"], value=m["value"]) for m in metrics
            ]
            self.metrics_repo.create_many(metric_objs)

        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=model.id,
            action="create",
            after=snapshot(model),
        )
        self.session.commit()
        return model

    def onnx_file(self, model_id: uuid.UUID) -> tuple[Model, Path]:
        """The model's ONNX graph on disk; 404 when it was never exported or the file is gone."""
        model = self.get_or_404(model_id)
        if not model.onnx_uri:
            raise NotFoundError(f"Model {model.name} v{model.version} has no ONNX export")
        path = uri_path(model.onnx_uri)
        if not path.is_file():
            raise NotFoundError(f"ONNX file for model {model.name} v{model.version} is missing")
        return model, path


def uri_path(uri: str) -> Path:
    """`file:///data/models/x` -> Path('/data/models/x'); a bare path passes through."""
    return Path(uri.removeprefix("file://"))


# Celery task states as the API reports them.
JOB_STATES = {"PENDING": "queued", "RECEIVED": "queued", "STARTED": "running", "RETRY": "running",
              "SUCCESS": "done", "FAILURE": "failed", "REVOKED": "failed"}  # fmt: skip


class JobService:
    """Celery job status for `GET /jobs/{id}` (training and benchmark jobs)."""

    def status(self, job_id: str) -> JobOut:
        from celery.result import AsyncResult

        from app.workers.celery_app import celery_app

        result = AsyncResult(job_id, app=celery_app)
        state = result.state
        model_id = None
        if state == "SUCCESS" and isinstance(result.result, dict) and result.result.get("model_id"):
            model_id = uuid.UUID(result.result["model_id"])
        # On FAILURE `result.result` is the raised exception, e.g. an unsupported task/dataset pair.
        error = str(result.result) if state == "FAILURE" and result.result is not None else None
        # Celery cannot tell an unknown id from a queued one (both are PENDING); report "queued".
        return JobOut(job_id=job_id, status=JOB_STATES.get(state, state.lower()), model_id=model_id, error=error)


class BenchmarkService:
    entity = "benchmark_runs"

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = BenchmarkRepository(session)

    def list_runs(self, params: PageParams) -> tuple[list[BenchmarkRun], int]:
        return self.repo.list_runs(params)

    def get_or_404(self, run_id: uuid.UUID) -> BenchmarkRun:
        run = self.repo.get(run_id)
        if run is None:
            raise NotFoundError(f"Benchmark run {run_id} not found")
        return run

    def start(self, actor: CurrentUser, body: BenchmarkRunRequest) -> BenchmarkRun:
        """Record a `running` row, audit it, then hand the work to the worker."""
        from twinvoice_pdm.benchmark import missing_datasets

        datasets = list(dict.fromkeys(body.datasets))
        missing = missing_datasets(datasets, get_settings().raw_data_dir)
        if missing:
            raise ConflictError(
                f"Raw data missing for {', '.join(missing)}: run `python data/download.py {' '.join(missing)}`",
                missing=missing,
            )

        run = self.repo.create(BenchmarkRun(seed=body.seed, datasets=datasets, status="running"))
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=run.id,
            action="run",
            after={**snapshot(run), "quick": body.quick},
        )
        self.session.commit()

        from app.workers.tasks.benchmark import run_benchmark_task

        try:
            run_benchmark_task.delay(str(run.id), quick=body.quick)
        except Exception as exc:
            # The row exists and says running; a broker outage must not leave it like that forever.
            run.status = "failed"
            run.results = {"_error": {"message": f"could not enqueue the benchmark job: {exc}"}}
            self.session.commit()
        return run

    def report_markdown(self, run_id: uuid.UUID) -> str:
        run = self.get_or_404(run_id)
        if not run.report_uri:
            raise NotFoundError("This benchmark run has no report yet")
        path = uri_path(run.report_uri)
        if not path.is_file():
            raise NotFoundError("The benchmark report file is missing")
        return path.read_text(encoding="utf-8")


class PredictionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = PredictionRepository(session)

    def query(self, asset_id: uuid.UUID, start: datetime, end: datetime) -> list[PredictionOut]:
        preds = self.repo.query(asset_id, start, end)
        return [PredictionOut.from_prediction(p) for p in preds]

    def latest(self, asset_id: uuid.UUID) -> Prediction | None:
        return self.repo.latest(asset_id)

    def write_prediction(self, prediction: Prediction) -> Prediction:
        self.repo.create(prediction)
        self.session.commit()
        return prediction
