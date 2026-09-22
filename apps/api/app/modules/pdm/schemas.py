"""Pydantic schemas for predictive maintenance (M5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Model ─────────────────────────────────────────────────────────────


class ModelOut(BaseModel):
    id: uuid.UUID
    name: str
    version: str
    task: str
    algorithm: str
    asset_type: str | None
    asset_id: uuid.UUID | None
    dataset_ref: str
    feature_set: list[str] | dict[str, Any]
    hyperparams: dict[str, Any]
    window_size: int | None
    stride: int | None
    horizon: int | None
    artifact_uri: str
    onnx_uri: str | None
    stage: str
    trained_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ModelMetricOut(BaseModel):
    id: uuid.UUID
    model_id: uuid.UUID
    split: str
    metric: str
    value: float
    extra: dict[str, Any] | None

    model_config = {"from_attributes": True}


class ModelPromote(BaseModel):
    """Promote a model to production stage."""

    pass


class TrainRequest(BaseModel):
    asset_type: str | None = None
    asset_id: uuid.UUID | None = None
    task: str = Field("rul", pattern="^(anomaly|failure|rul|survival)$")
    algorithm: str = "lightgbm"
    dataset_ref: str | None = None
    window_size: int = Field(60, ge=10, le=600)
    stride: int = Field(10, ge=1, le=60)
    horizon: int = Field(30, ge=1, le=500)
    hyperparams: dict[str, Any] = Field(default_factory=dict)


class JobOut(BaseModel):
    job_id: str
    status: str
    model_id: uuid.UUID | None = None
    # The worker's exception message when the job failed, so the UI can say why.
    error: str | None = None


# ── Prediction ────────────────────────────────────────────────────────


class RulOut(BaseModel):
    point: float | None
    low: float | None
    high: float | None
    unit: str
    coverage: float | None


class ConfidenceOut(BaseModel):
    label: str | None
    reasons: list[str]


class DriftOut(BaseModel):
    flag: bool
    score: float | None


class PredictionOut(BaseModel):
    id: uuid.UUID
    time: datetime
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    model_id: uuid.UUID
    health_index: float | None
    anomaly_score: float | None
    failure_probability: dict[str, float] | None
    failure_probability_calibrated: dict[str, float] | None
    rul: RulOut
    confidence: ConfidenceOut
    drift: DriftOut
    source: str
    latency_ms: int | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_prediction(cls, p: Any) -> PredictionOut:
        return cls(
            id=p.id,
            time=p.time,
            asset_id=p.asset_id,
            component_id=p.component_id,
            model_id=p.model_id,
            health_index=float(p.health_index) if p.health_index is not None else None,
            anomaly_score=p.anomaly_score,
            failure_probability=p.failure_probability,
            failure_probability_calibrated=p.failure_probability_calibrated,
            rul=RulOut(
                point=p.rul_point,
                low=p.rul_low,
                high=p.rul_high,
                unit=p.rul_unit or "cycles",
                coverage=float(p.rul_coverage) if p.rul_coverage is not None else None,
            ),
            confidence=ConfidenceOut(label=p.confidence_label, reasons=list(p.confidence_reasons or [])),
            drift=DriftOut(flag=p.drift_flag, score=p.drift_score),
            source=p.source,
            latency_ms=p.latency_ms,
        )


class PredictionLatest(BaseModel):
    asset_code: str
    prediction: PredictionOut | None


# ── Benchmark ─────────────────────────────────────────────────────────


BENCHMARK_DATASETS = ("FD001", "FD002", "FD003", "FD004", "AI4I", "METROPT3")
BenchmarkDataset = Literal["FD001", "FD002", "FD003", "FD004", "AI4I", "METROPT3"]


class BenchmarkTarget(BaseModel):
    op: Literal["le", "ge"]
    value: float


class BenchmarkRunRequest(BaseModel):
    datasets: list[BenchmarkDataset] = Field(min_length=1)
    seed: int = Field(42, ge=0)
    quick: bool = False


class BenchmarkOut(BaseModel):
    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    git_sha: str | None
    seed: int
    datasets: list[str]
    results: dict[str, dict[str, float]] | None
    report_uri: str | None
    status: Literal["running", "done", "failed"]
    # No column of its own: a failed run keeps its message under results["_error"], which is lifted
    # out here so `results` stays the {dataset: {metric: value}} shape the report template reads.
    error: str | None = None
    targets: dict[str, dict[str, BenchmarkTarget]] = Field(default_factory=dict)

    @classmethod
    def from_run(cls, run: Any, targets: dict[str, dict[str, dict[str, Any]]]) -> BenchmarkOut:
        raw = dict(run.results or {})
        error = raw.pop("_error", None)
        return cls(
            id=run.id,
            started_at=run.started_at,
            finished_at=run.finished_at,
            git_sha=run.git_sha,
            seed=run.seed,
            datasets=list(run.datasets or []),
            results=raw or None,
            report_uri=run.report_uri,
            status=run.status,
            error=error.get("message") if isinstance(error, dict) else None,
            targets={d: {m: BenchmarkTarget(**t) for m, t in metrics.items()} for d, metrics in targets.items()},
        )
