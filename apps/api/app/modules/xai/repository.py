"""Repository layer for explainable AI (M6)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.xai.models import (
    Counterfactual,
    Explanation,
    ExplanationFeedback,
    ExplanationQualityMetric,
    KnowledgeBaseEntry,
    Narration,
    NarrationAudit,
)


class ExplanationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, explanation_id: uuid.UUID) -> Explanation | None:
        return self.session.get(Explanation, explanation_id)

    def by_prediction(self, prediction_id: uuid.UUID) -> Explanation | None:
        return self.session.scalars(select(Explanation).where(Explanation.prediction_id == prediction_id)).first()

    def create(self, explanation: Explanation) -> Explanation:
        self.session.add(explanation)
        self.session.flush()
        return explanation

    def counterfactuals(self, explanation_id: uuid.UUID) -> list[Counterfactual]:
        return list(
            self.session.scalars(
                select(Counterfactual)
                .where(Counterfactual.explanation_id == explanation_id)
                .order_by(Counterfactual.created_at.desc())
            )
        )

    def add_counterfactual(self, counterfactual: Counterfactual) -> Counterfactual:
        self.session.add(counterfactual)
        self.session.flush()
        return counterfactual


class NarrationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, explanation_id: uuid.UUID, kind: str, lang: str) -> Narration | None:
        return self.session.scalars(
            select(Narration).where(
                Narration.explanation_id == explanation_id,
                Narration.kind == kind,
                Narration.lang == lang,
            )
        ).first()

    def create(self, narration: Narration) -> Narration:
        self.session.add(narration)
        self.session.flush()
        return narration

    def add_audit(self, audit: NarrationAudit) -> NarrationAudit:
        self.session.add(audit)
        self.session.flush()
        return audit

    def audit_for(self, narration_id: uuid.UUID) -> NarrationAudit | None:
        return self.session.scalars(
            select(NarrationAudit)
            .where(NarrationAudit.narration_id == narration_id)
            .order_by(NarrationAudit.created_at.desc())
        ).first()

    def audits(
        self,
        *,
        model_id: uuid.UUID | None = None,
        passed: bool | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[tuple[NarrationAudit, Narration]]:
        stmt = self._audit_select()
        if passed is not None:
            stmt = stmt.where(NarrationAudit.passed.is_(passed))
        if since is not None:
            stmt = stmt.where(NarrationAudit.created_at >= since)
        if model_id is not None:
            stmt = stmt.where(Explanation.id.in_(self._explanations_for_model(model_id)))
        rows = self.session.execute(stmt.order_by(NarrationAudit.created_at.desc()).limit(limit)).all()
        return [(audit, narration) for audit, narration in rows]

    def pass_rate(self, model_id: uuid.UUID | None = None) -> tuple[float | None, int]:
        stmt = select(
            func.count(NarrationAudit.id),
            func.count(NarrationAudit.id).filter(NarrationAudit.passed.is_(True)),
        )
        if model_id is not None:
            stmt = stmt.join(Narration, Narration.id == NarrationAudit.narration_id).where(
                Narration.explanation_id.in_(self._explanations_for_model(model_id))
            )
        total, passed = self.session.execute(stmt).one()
        return (passed / total if total else None), total

    def _audit_select(self) -> Select[tuple[NarrationAudit, Narration]]:
        return (
            select(NarrationAudit, Narration)
            .join(Narration, Narration.id == NarrationAudit.narration_id)
            .join(Explanation, Explanation.id == Narration.explanation_id)
        )

    def _explanations_for_model(self, model_id: uuid.UUID) -> Select[tuple[uuid.UUID]]:
        """Explanations belong to a model only through their prediction, which carries no FK here."""
        from app.modules.pdm.models import Prediction

        return select(Explanation.id).where(
            Explanation.prediction_id.in_(select(Prediction.id).where(Prediction.model_id == model_id))
        )


class FeedbackRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, feedback: ExplanationFeedback) -> ExplanationFeedback:
        self.session.add(feedback)
        self.session.flush()
        return feedback

    def for_explanation(self, explanation_id: uuid.UUID) -> list[ExplanationFeedback]:
        return list(
            self.session.scalars(
                select(ExplanationFeedback)
                .where(ExplanationFeedback.explanation_id == explanation_id)
                .order_by(ExplanationFeedback.created_at.desc())
            )
        )


class QualityMetricRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def for_model(self, model_id: uuid.UUID, metric: str | None = None) -> list[ExplanationQualityMetric]:
        stmt = select(ExplanationQualityMetric).where(ExplanationQualityMetric.model_id == model_id)
        if metric:
            stmt = stmt.where(ExplanationQualityMetric.metric == metric)
        return list(self.session.scalars(stmt.order_by(ExplanationQualityMetric.computed_at.desc())))

    def create_many(self, metrics: list[ExplanationQualityMetric]) -> None:
        self.session.add_all(metrics)
        self.session.flush()


class KnowledgeBaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def for_failure_mode(self, failure_mode_id: uuid.UUID, lang: str = "en") -> KnowledgeBaseEntry | None:
        entry = self.session.scalars(
            select(KnowledgeBaseEntry).where(
                KnowledgeBaseEntry.failure_mode_id == failure_mode_id, KnowledgeBaseEntry.lang == lang
            )
        ).first()
        if entry is not None or lang == "en":
            return entry
        return self.for_failure_mode(failure_mode_id, "en")

    def upsert(self, entry: KnowledgeBaseEntry) -> KnowledgeBaseEntry:
        existing = self.for_failure_mode(entry.failure_mode_id, entry.lang)
        if existing is None:
            self.session.add(entry)
            self.session.flush()
            return entry
        for field in ("symptom", "likely_cause", "recommended_action", "parts", "est_duration_min"):
            setattr(existing, field, getattr(entry, field))
        self.session.flush()
        return existing
