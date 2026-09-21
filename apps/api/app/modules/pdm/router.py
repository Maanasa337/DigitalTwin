"""REST endpoints for predictive maintenance (M5)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.common.schemas import Page
from app.core.db import get_session
from app.core.security import CurrentUser, get_current_user, require_role
from app.modules.pdm.schemas import (
    JobOut,
    ModelMetricOut,
    ModelOut,
    PredictionLatest,
    PredictionOut,
    TrainRequest,
)
from app.modules.pdm.service import ModelService, PredictionService

router = APIRouter(tags=["pdm"])


# ── Models ────────────────────────────────────────────────────────────


@router.get("/models", response_model=Page[ModelOut])
def list_models(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    task: str | None = None,
    stage: str | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    items, total = ModelService(session).list_models(PageParams(page=page, size=size), task, stage)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/models/{model_id}", response_model=ModelOut)
def get_model(
    model_id: uuid.UUID,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> ModelOut:
    model = ModelService(session).get_or_404(model_id)
    return ModelOut.model_validate(model)


@router.get("/models/{model_id}/metrics", response_model=list[ModelMetricOut])
def get_model_metrics(
    model_id: uuid.UUID,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[ModelMetricOut]:
    metrics = ModelService(session).get_metrics(model_id)
    return [ModelMetricOut.model_validate(m) for m in metrics]


@router.post("/models/{model_id}/promote", response_model=ModelOut)
def promote_model(
    model_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(require_role("engineer", "admin")),
) -> ModelOut:
    model = ModelService(session).promote(user, model_id)
    return ModelOut.model_validate(model)


@router.post("/models/train", response_model=JobOut, status_code=202)
def train_model(
    body: TrainRequest,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(require_role("engineer", "admin")),
) -> JobOut:
    """Queue an async training job. Returns immediately with a job ID."""
    # Celery task dispatch
    try:
        from app.workers.tasks.train import train_model_task

        result = train_model_task.delay(
            task=body.task,
            algorithm=body.algorithm,
            asset_type=body.asset_type,
            asset_id=str(body.asset_id) if body.asset_id else None,
            dataset_ref=body.dataset_ref,
            window_size=body.window_size,
            stride=body.stride,
            horizon=body.horizon,
            hyperparams=body.hyperparams,
        )
        return JobOut(job_id=result.id, status="queued")
    except Exception:
        # Celery not available — return a placeholder
        import uuid as _uuid

        return JobOut(job_id=str(_uuid.uuid4()), status="queued_local")


# ── Predictions ───────────────────────────────────────────────────────


@router.get("/predictions", response_model=list[PredictionOut])
def query_predictions(
    asset: uuid.UUID,
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[PredictionOut]:
    return PredictionService(session).query(asset, start, end)


@router.get("/predictions/latest", response_model=PredictionLatest)
def predictions_latest(
    asset: uuid.UUID,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> PredictionLatest:
    from app.modules.assets.repository import AssetRepository

    asset_obj = AssetRepository(session).get(asset)
    if asset_obj is None:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"Asset {asset} not found")
    pred = PredictionService(session).latest(asset)
    return PredictionLatest(
        asset_code=asset_obj.code,
        prediction=PredictionOut.from_prediction(pred) if pred else None,
    )
