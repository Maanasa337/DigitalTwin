"""Pydantic schemas for explainable AI (M6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.common.schemas import ORMModel

Lang = Literal["en", "hi"]
NarrationKind = Literal["status", "why", "confidence", "counterfactual", "report_summary"]
Verdict = Literal["agree", "disagree", "unsure"]
Channel = Literal["ui", "voice", "chat"]


# ── Explanation ───────────────────────────────────────────────────────


class AttributionOut(BaseModel):
    feature: str
    label: str
    value: float
    unit: str
    contribution: float
    direction: str
    share: float
    rank: int


class ReasonCardOut(BaseModel):
    symptom: str
    evidence: list[dict[str, Any]]
    likely_cause: str
    action: str
    confidence: float
    failure_mode: str
    parts: list[str] = Field(default_factory=list)
    est_duration_min: int | None = None
    kb_entry_id: str | None = None


class ExplanationOut(ORMModel):
    id: uuid.UUID
    prediction_id: uuid.UUID
    created_at: datetime
    method: str
    base_value: float | None
    attributions: list[AttributionOut]
    temporal_attribution: dict[str, Any] | None
    ebm_terms: dict[str, Any] | None
    agreement: dict[str, Any] | None
    reason_card: ReasonCardOut | None
    compute_ms: int | None


class CounterfactualOut(ORMModel):
    id: uuid.UUID
    explanation_id: uuid.UUID
    created_at: datetime
    target: str
    changes: list[dict[str, Any]]
    outcome: dict[str, Any]
    feasibility_score: float | None
    action_text: str | None


# ── Narration ─────────────────────────────────────────────────────────


class NarrationAuditOut(ORMModel):
    id: uuid.UUID
    narration_id: uuid.UUID
    rank_agreement: float
    sign_agreement: float
    numeric_within_tolerance: bool
    hallucinated_features: list[str]
    unsupported_recommendation: bool
    passed: bool
    details: dict[str, Any] | None
    created_at: datetime


class NarrationOut(ORMModel):
    id: uuid.UUID
    explanation_id: uuid.UUID
    kind: str
    lang: str
    template_text: str
    llm_text: str | None
    llm_model: str | None
    final_text: str
    created_at: datetime
    audit: NarrationAuditOut | None = None


class NarrationAuditRow(BaseModel):
    """A row on /explain/quality: the audit plus enough of the narration to make it readable."""

    audit: NarrationAuditOut
    kind: str
    lang: str
    final_text: str
    used_llm: bool


# ── Feedback ──────────────────────────────────────────────────────────


class FeedbackCreate(BaseModel):
    verdict: Verdict
    reason: str | None = Field(None, max_length=1000)
    suspect_sensor_id: uuid.UUID | None = None
    channel: Channel = "ui"


class FeedbackOut(ORMModel):
    id: uuid.UUID
    explanation_id: uuid.UUID
    user_id: uuid.UUID | None
    verdict: str
    reason: str | None
    suspect_sensor_id: uuid.UUID | None
    channel: str
    created_at: datetime


# ── Model-level quality ───────────────────────────────────────────────


class GlobalImportanceOut(BaseModel):
    model_id: uuid.UUID
    method: str
    features: list[dict[str, Any]]
    partial_dependence: dict[str, list[list[float]]] = Field(default_factory=dict)


class QualityMetricOut(ORMModel):
    id: uuid.UUID
    model_id: uuid.UUID
    method: str
    metric: str
    value: float
    dataset_ref: str | None
    computed_at: datetime


class QualityMetricsOut(BaseModel):
    model_id: uuid.UUID
    metrics: list[QualityMetricOut]
    narration_audit_pass_rate: float | None = None
    narration_audit_count: int = 0
