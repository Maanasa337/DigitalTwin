"""Service layer for predictive maintenance models and predictions (M5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.core.audit import snapshot, write_audit
from app.core.errors import ConflictError, NotFoundError
from app.core.security import CurrentUser
from app.modules.pdm.models import Model, ModelMetric, Prediction
from app.modules.pdm.repository import ModelMetricRepository, ModelRepository, PredictionRepository
from app.modules.pdm.schemas import PredictionOut


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
