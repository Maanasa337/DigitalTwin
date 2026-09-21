"""ORM models for predictive maintenance (M5): models, metrics, predictions, benchmarks."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Numeric, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, PKMixin, TimestampMixin

MODEL_TASKS = ("anomaly", "failure", "rul", "survival")
MODEL_STAGES = ("candidate", "production", "archived")
PREDICTION_SOURCES = ("server", "edge")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(v) for v in values)})"


class Model(PKMixin, TimestampMixin, Base):
    __tablename__ = "models"
    __table_args__ = (
        Index("models_name_version_uq", "name", "version", unique=True),
        # One production model per (name, asset); a plant-wide model has a null asset_id, so the
        # coalesce gives those rows a shared sentinel the unique index can actually compare.
        Index(
            "models_one_production_uq",
            "name",
            text("coalesce(asset_id,'00000000-0000-0000-0000-000000000000'::uuid)"),
            unique=True,
            postgresql_where=text("stage='production'"),
        ),
        CheckConstraint(_in("task", MODEL_TASKS), name="task"),
        CheckConstraint(_in("stage", MODEL_STAGES), name="stage"),
    )

    name: Mapped[str]
    version: Mapped[str]
    task: Mapped[str]
    algorithm: Mapped[str]
    asset_type: Mapped[str | None]
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id"))
    dataset_ref: Mapped[str]
    dataset_hash: Mapped[str]
    feature_set: Mapped[dict[str, Any]]
    hyperparams: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    window_size: Mapped[int | None]
    stride: Mapped[int | None]
    horizon: Mapped[int | None]
    artifact_uri: Mapped[str]
    onnx_uri: Mapped[str | None]
    explainer_uri: Mapped[str | None]
    calibrator_uri: Mapped[str | None]
    conformal_uri: Mapped[str | None]
    stage: Mapped[str] = mapped_column(server_default="candidate")
    trained_at: Mapped[datetime] = mapped_column(server_default=func.now())
    trained_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class ModelMetric(PKMixin, Base):
    __tablename__ = "model_metrics"
    __table_args__ = (
        CheckConstraint("split in ('train','val','test','calibration')", name="split"),
        Index("ix_model_metrics_model_id", "model_id"),
    )

    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"))
    split: Mapped[str]
    metric: Mapped[str]
    value: Mapped[float] = mapped_column(Float)
    extra: Mapped[dict[str, Any] | None]


class Prediction(PKMixin, Base):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_asset_id_time", "asset_id", text("time DESC")),
        # `predictions` is a hypertable, so it carries no primary key: Timescale refuses a unique
        # index that omits the partitioning column. These two carry the identity instead.
        Index("predictions_time_id_uq", "time", "id", unique=True),
        Index("ix_predictions_id", "id"),
        CheckConstraint(
            "confidence_label in ('high','medium','low') OR confidence_label IS NULL",
            name="confidence_label",
        ),
        CheckConstraint(_in("source", PREDICTION_SOURCES), name="source"),
    )

    time: Mapped[datetime] = mapped_column(server_default=func.now())
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"))
    component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("components.id"))
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"))
    window_start: Mapped[datetime]
    window_end: Mapped[datetime]
    health_index: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    anomaly_score: Mapped[float | None] = mapped_column(Float)
    failure_probability: Mapped[dict[str, Any] | None]
    failure_probability_calibrated: Mapped[dict[str, Any] | None]
    rul_point: Mapped[float | None] = mapped_column(Float)
    rul_low: Mapped[float | None] = mapped_column(Float)
    rul_high: Mapped[float | None] = mapped_column(Float)
    rul_unit: Mapped[str | None] = mapped_column(server_default="cycles")
    rul_coverage: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), server_default="0.90")
    rul_physics_point: Mapped[float | None] = mapped_column(Float)
    rul_fused_point: Mapped[float | None] = mapped_column(Float)
    confidence_label: Mapped[str | None]
    confidence_reasons: Mapped[list[str]] = mapped_column(server_default=text("'{}'"))
    drift_flag: Mapped[bool] = mapped_column(Boolean, server_default="false")
    drift_score: Mapped[float | None] = mapped_column(Float)
    ood_score: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(server_default="server")
    latency_ms: Mapped[int | None]


class BenchmarkRun(PKMixin, Base):
    __tablename__ = "benchmark_runs"

    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
    git_sha: Mapped[str | None]
    seed: Mapped[int]
    datasets: Mapped[list[str]]
    results: Mapped[dict[str, Any] | None]
    report_uri: Mapped[str | None]
    status: Mapped[str] = mapped_column(server_default="running")
