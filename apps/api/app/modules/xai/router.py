"""REST endpoints for explainable AI (M6)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import ServiceUnavailableError
from app.core.security import CurrentUser, get_current_user, require_role
from app.modules.xai.schemas import (
    CounterfactualOut,
    ExplanationOut,
    FeedbackCreate,
    FeedbackOut,
    GlobalImportanceOut,
    Lang,
    NarrationAuditRow,
    NarrationKind,
    NarrationOut,
    QualityMetricsOut,
)
from app.modules.xai.service import ExplanationService, QualityService

router = APIRouter(tags=["xai"])
reader = Depends(get_current_user)


@router.get("/explanations/{explanation_id}", response_model=ExplanationOut, dependencies=[reader])
def get_explanation(explanation_id: uuid.UUID, session: Session = Depends(get_session)) -> Any:
    return ExplanationService(session).get_or_404(explanation_id)


@router.get("/predictions/{prediction_id}/explanation", response_model=ExplanationOut, dependencies=[reader])
def get_explanation_for_prediction(prediction_id: uuid.UUID, session: Session = Depends(get_session)) -> Any:
    return ExplanationService(session).by_prediction_or_404(prediction_id)


@router.get(
    "/explanations/{explanation_id}/counterfactual",
    response_model=list[CounterfactualOut],
    dependencies=[reader],
)
def get_counterfactuals(explanation_id: uuid.UUID, session: Session = Depends(get_session)) -> Any:
    return ExplanationService(session).counterfactuals(explanation_id)


@router.get("/explanations/{explanation_id}/narration", response_model=NarrationOut, dependencies=[reader])
def get_narration(
    explanation_id: uuid.UUID,
    kind: NarrationKind = "why",
    lang: Lang = "en",
    session: Session = Depends(get_session),
) -> Any:
    narration, audit = ExplanationService(session).narration(explanation_id, kind, lang)
    return NarrationOut.model_validate(narration).model_copy(update={"audit": audit})


@router.post(
    "/explanations/{explanation_id}/feedback",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
)
def create_feedback(
    explanation_id: uuid.UUID,
    data: FeedbackCreate,
    user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Any:
    return ExplanationService(session).add_feedback(user, explanation_id, data)


# ── Model-level explanation quality ───────────────────────────────────


@router.get("/models/{model_id}/global-importance", response_model=GlobalImportanceOut, dependencies=[reader])
def global_importance(model_id: uuid.UUID, session: Session = Depends(get_session)) -> Any:
    return QualityService(session).global_importance(model_id)


@router.get("/models/{model_id}/quality-metrics", response_model=QualityMetricsOut, dependencies=[reader])
def quality_metrics(model_id: uuid.UUID, session: Session = Depends(get_session)) -> Any:
    return QualityService(session).for_model(model_id)


@router.post("/models/{model_id}/quality-metrics/refresh", status_code=status.HTTP_202_ACCEPTED)
def refresh_quality_metrics(
    model_id: uuid.UUID,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(require_role("engineer", "admin")),
) -> dict[str, str]:
    """Recompute importance and explanation quality for one model in the worker."""
    QualityService(session).model_or_404(model_id)
    try:
        from app.workers.tasks.insights import compute_model_insights

        compute_model_insights.delay(str(model_id))
    except Exception as exc:
        raise ServiceUnavailableError("Task queue unavailable; recompute was not queued") from exc
    return {"status": "queued"}


@router.get("/narration-audits", response_model=list[NarrationAuditRow], dependencies=[reader])
def narration_audits(
    model: uuid.UUID | None = None,
    passed: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> Any:
    return QualityService(session).audits(model, passed, limit)
