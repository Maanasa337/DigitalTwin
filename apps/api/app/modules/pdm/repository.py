"""Repository layer for PDM models and predictions (M5)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, select, update
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.common.repository import CrudRepository
from app.modules.pdm.models import BenchmarkRun, Model, ModelMetric, Prediction


class ModelRepository(CrudRepository[Model]):
    model = Model
    sortable = frozenset({"created_at", "name", "trained_at", "stage"})

    def get_by_name_version(self, name: str, version: str) -> Model | None:
        return self.session.scalars(select(Model).where(Model.name == name, Model.version == version)).first()

    def production_model(self, name: str, asset_id: uuid.UUID | None = None) -> Model | None:
        stmt = select(Model).where(Model.name == name, Model.stage == "production")
        stmt = stmt.where(Model.asset_id == asset_id) if asset_id else stmt.where(Model.asset_id.is_(None))
        return self.session.scalars(stmt).first()

    def promote(self, model: Model) -> None:
        """Set model to production, archive previous production model with same name scope."""
        # Demote existing production model
        self.session.execute(
            update(Model)
            .where(
                Model.name == model.name,
                Model.stage == "production",
                Model.id != model.id,
            )
            .values(stage="archived")
        )
        model.stage = "production"
        self.session.flush()

    def list_with_metrics(
        self, params: PageParams, task: str | None = None, stage: str | None = None
    ) -> tuple[list[Model], int]:
        filters: list[ColumnElement[bool]] = []
        if task:
            filters.append(Model.task == task)
        if stage:
            filters.append(Model.stage == stage)
        return self.list(params, filters)


class ModelMetricRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def for_model(self, model_id: uuid.UUID) -> list[ModelMetric]:
        return list(self.session.scalars(select(ModelMetric).where(ModelMetric.model_id == model_id)))

    def create_many(self, metrics: list[ModelMetric]) -> None:
        self.session.add_all(metrics)
        self.session.flush()


class PredictionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def query(
        self,
        asset_id: uuid.UUID,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> list[Prediction]:
        return list(
            self.session.scalars(
                select(Prediction)
                .where(
                    Prediction.asset_id == asset_id,
                    Prediction.time >= start,
                    Prediction.time < end,
                )
                .order_by(Prediction.time)
                .limit(limit)
            )
        )

    def latest(self, asset_id: uuid.UUID) -> Prediction | None:
        return self.session.scalars(
            select(Prediction).where(Prediction.asset_id == asset_id).order_by(Prediction.time.desc()).limit(1)
        ).first()

    def create(self, prediction: Prediction) -> Prediction:
        self.session.add(prediction)
        self.session.flush()
        return prediction


class BenchmarkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_runs(self) -> list[BenchmarkRun]:
        return list(self.session.scalars(select(BenchmarkRun).order_by(BenchmarkRun.started_at.desc()).limit(50)))

    def create(self, run: BenchmarkRun) -> BenchmarkRun:
        self.session.add(run)
        self.session.flush()
        return run
