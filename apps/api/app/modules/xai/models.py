"""ORM models for explainable AI (M6): explanations, counterfactuals, narrations, audits, feedback, quality."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, PKMixin, TimestampMixin

ATTRIBUTION_METHODS = ("tree_shap", "deep_shap", "integrated_gradients", "kernel_shap", "ebm")
NARRATION_KINDS = ("status", "why", "confidence", "counterfactual", "report_summary")
FEEDBACK_VERDICTS = ("agree", "disagree", "unsure")
FEEDBACK_CHANNELS = ("ui", "voice", "chat")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(v) for v in values)})"


class KnowledgeBaseEntry(PKMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_base_entries"
    __table_args__ = (Index("knowledge_base_entries_mode_lang_uq", "failure_mode_id", "lang", unique=True),)

    failure_mode_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("failure_modes.id"))
    symptom: Mapped[str] = mapped_column(Text)
    likely_cause: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text)
    parts: Mapped[list[str]] = mapped_column(server_default=text("'{}'"))
    est_duration_min: Mapped[int | None]
    lang: Mapped[str] = mapped_column(server_default="en")


class Explanation(PKMixin, Base):
    __tablename__ = "explanations"
    __table_args__ = (
        CheckConstraint(_in("method", ATTRIBUTION_METHODS), name="method"),
        Index("explanations_prediction_id_uq", "prediction_id", unique=True),
    )

    prediction_id: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    method: Mapped[str]
    base_value: Mapped[float | None] = mapped_column(Float)
    # A JSON array, so it needs JSONB explicitly: the Base type map only covers dict[str, Any].
    attributions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    temporal_attribution: Mapped[dict[str, Any] | None]
    ebm_terms: Mapped[dict[str, Any] | None]
    agreement: Mapped[dict[str, Any] | None]
    reason_card: Mapped[dict[str, Any] | None]
    compute_ms: Mapped[int | None]


class Counterfactual(PKMixin, Base):
    __tablename__ = "counterfactuals"
    __table_args__ = (Index("ix_counterfactuals_explanation_id", "explanation_id"),)

    explanation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("explanations.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    target: Mapped[str]
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    outcome: Mapped[dict[str, Any]]
    feasibility_score: Mapped[float | None] = mapped_column(Float)
    action_text: Mapped[str | None] = mapped_column(Text)


class Narration(PKMixin, Base):
    __tablename__ = "narrations"
    __table_args__ = (
        CheckConstraint(_in("kind", NARRATION_KINDS), name="kind"),
        Index("narrations_explanation_kind_lang_uq", "explanation_id", "kind", "lang", unique=True),
    )

    explanation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("explanations.id"))
    kind: Mapped[str]
    lang: Mapped[str] = mapped_column(server_default="en")
    template_text: Mapped[str] = mapped_column(Text)
    llm_text: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None]
    llm_prompt_hash: Mapped[str | None]
    final_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class NarrationAudit(PKMixin, Base):
    __tablename__ = "narration_audits"
    __table_args__ = (
        Index("ix_narration_audits_narration_id", "narration_id"),
        Index("ix_narration_audits_created_at", text("created_at desc")),
    )

    narration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("narrations.id"))
    rank_agreement: Mapped[float] = mapped_column(Float)
    sign_agreement: Mapped[float] = mapped_column(Float)
    numeric_within_tolerance: Mapped[bool] = mapped_column(Boolean)
    hallucinated_features: Mapped[list[str]] = mapped_column(server_default=text("'{}'"))
    unsupported_recommendation: Mapped[bool] = mapped_column(Boolean, server_default="false")
    passed: Mapped[bool] = mapped_column(Boolean)
    details: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ExplanationFeedback(PKMixin, Base):
    __tablename__ = "explanation_feedback"
    __table_args__ = (
        CheckConstraint(_in("verdict", FEEDBACK_VERDICTS), name="verdict"),
        CheckConstraint(_in("channel", FEEDBACK_CHANNELS), name="channel"),
        Index("ix_explanation_feedback_explanation_id", "explanation_id"),
    )

    explanation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("explanations.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verdict: Mapped[str]
    reason: Mapped[str | None] = mapped_column(Text)
    suspect_sensor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sensors.id"))
    channel: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ExplanationQualityMetric(PKMixin, Base):
    __tablename__ = "explanation_quality_metrics"
    __table_args__ = (Index("ix_explanation_quality_metrics_model_id_metric", "model_id", "metric"),)

    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"))
    method: Mapped[str]
    metric: Mapped[str]
    value: Mapped[float] = mapped_column(Float)
    dataset_ref: Mapped[str | None]
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
