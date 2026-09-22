"""Service layer for explainable AI (M6).

The explanation itself is computed by the `explain` worker; this layer reads it back, narrates it on
demand, audits any LLM paraphrase before it is shown, and records operator feedback.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session
from twinvoice_xai.attribution import Attribution
from twinvoice_xai.audit import audit_narration
from twinvoice_xai.confidence import assess_confidence
from twinvoice_xai.llm import paraphrase
from twinvoice_xai.templates import narrate, status_context, why

from app.core.audit import ensure_user, write_audit
from app.core.config import get_settings
from app.core.errors import NotFoundError, UnprocessableError
from app.core.security import CurrentUser
from app.modules.assets.models import Sensor
from app.modules.xai.models import Explanation, ExplanationFeedback, Narration, NarrationAudit
from app.modules.xai.repository import (
    ExplanationRepository,
    FeedbackRepository,
    NarrationRepository,
    QualityMetricRepository,
)
from app.modules.xai.schemas import FeedbackCreate

SENSOR_FLAG_HOURS = 1  # FR-XAI-09: a disagree verdict suppresses that sensor's confidence for an hour


def to_attributions(rows: list[dict[str, Any]]) -> list[Attribution]:
    """Rehydrate the stored JSON into the dataclass the narration and audit helpers expect."""
    return [
        Attribution(
            feature=row["feature"],
            label=row["label"],
            value=float(row["value"]),
            unit=row.get("unit", ""),
            contribution=float(row["contribution"]),
            direction=row.get("direction", "neutral"),
            share=float(row.get("share", 0.0)),
            rank=int(row.get("rank", 0)),
        )
        for row in rows
    ]


class ExplanationService:
    entity = "explanations"

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ExplanationRepository(session)
        self.narrations = NarrationRepository(session)
        self.feedback = FeedbackRepository(session)

    def get_or_404(self, explanation_id: uuid.UUID) -> Explanation:
        obj = self.repo.get(explanation_id)
        if obj is None:
            raise NotFoundError(f"Explanation {explanation_id} not found")
        return obj

    def by_prediction_or_404(self, prediction_id: uuid.UUID) -> Explanation:
        obj = self.repo.by_prediction(prediction_id)
        if obj is None:
            raise NotFoundError(f"No explanation for prediction {prediction_id}")
        return obj

    def counterfactuals(self, explanation_id: uuid.UUID) -> list[Any]:
        self.get_or_404(explanation_id)
        return self.repo.counterfactuals(explanation_id)

    # ── Narration ─────────────────────────────────────────────────────

    def narration(self, explanation_id: uuid.UUID, kind: str, lang: str) -> tuple[Narration, NarrationAudit | None]:
        """Return the cached narration, or compose, audit and store one.

        The template text is always written first, so a failed or unavailable LLM still leaves a
        narration row — the UI never has to handle "explained but unnarratable".
        """
        existing = self.narrations.get(explanation_id, kind, lang)
        if existing is not None:
            return existing, self.narrations.audit_for(existing.id)

        explanation = self.get_or_404(explanation_id)
        attributions = to_attributions(explanation.attributions or [])
        template_text = self._template_text(explanation, attributions, kind, lang)

        narration = Narration(
            explanation_id=explanation_id,
            kind=kind,
            lang=lang,
            template_text=template_text,
            final_text=template_text,
        )

        candidate = paraphrase(
            {
                "attributions": explanation.attributions,
                "reason_card": explanation.reason_card,
                "agreement": explanation.agreement,
            },
            template_text,
            endpoint=get_settings().llm_endpoint,
            lang=lang,
        )

        audit_row: NarrationAudit | None = None
        if candidate is not None:
            result = audit_narration(
                candidate.text,
                attributions,
                recommended_actions=[(explanation.reason_card or {}).get("action", "")],
            )
            narration.llm_text = candidate.text
            narration.llm_model = candidate.model
            narration.llm_prompt_hash = candidate.prompt_hash
            if result.passed:
                narration.final_text = candidate.text
            self.narrations.create(narration)
            audit_row = self.narrations.add_audit(NarrationAudit(narration_id=narration.id, **result.to_dict()))
        else:
            self.narrations.create(narration)

        self.session.commit()
        return narration, audit_row

    def _template_text(self, explanation: Explanation, attributions: list[Attribution], kind: str, lang: str) -> str:
        if kind == "why":
            if not attributions:
                raise UnprocessableError("Explanation has no attributions to narrate")
            return why(attributions, lang)

        if kind == "counterfactual":
            counterfactuals = self.repo.counterfactuals(explanation.id)
            if not counterfactuals:
                return narrate("counterfactual", {"target": "a healthy state", "action": ""}, lang)
            best = counterfactuals[0]
            outcome = next(iter((best.outcome or {}).values()), 0.0)
            return narrate(
                "counterfactual",
                {"action": best.action_text or "", "outcome": float(outcome), "unit": "cycles"},
                lang,
            )

        if kind == "confidence":
            agreement = (explanation.agreement or {}).get("shap_vs_ebm_top3_jaccard")
            result = assess_confidence(model_agreement=agreement)
            return narrate("confidence", {"label": result.label, "reasons": " ".join(result.reasons)}, lang)

        card = explanation.reason_card or {}
        health = float(card.get("confidence", 0.0)) * 100
        return narrate(
            "status",
            status_context(card.get("failure_mode", "The asset"), health, None, None, None, "cycles", lang),
            lang,
        )

    # ── Feedback (FR-XAI-09) ──────────────────────────────────────────

    def add_feedback(self, actor: CurrentUser, explanation_id: uuid.UUID, data: FeedbackCreate) -> ExplanationFeedback:
        """Record the verdict and, when it names a sensor, flag that sensor for an hour.

        The flag and the feedback row are written in one transaction: a flagged sensor with no
        recorded reason would be impossible for an engineer to interpret later.
        """
        self.get_or_404(explanation_id)
        if data.suspect_sensor_id is not None and data.verdict != "disagree":
            raise UnprocessableError("A suspect sensor can only be reported with a 'disagree' verdict")

        feedback = ExplanationFeedback(
            explanation_id=explanation_id,
            user_id=ensure_user(self.session, actor),
            verdict=data.verdict,
            reason=data.reason,
            suspect_sensor_id=data.suspect_sensor_id,
            channel=data.channel,
        )
        self.feedback.create(feedback)

        if data.suspect_sensor_id is not None:
            sensor = self.session.get(Sensor, data.suspect_sensor_id)
            if sensor is None:
                raise NotFoundError(f"Sensor {data.suspect_sensor_id} not found")
            sensor.quality_flag = "suspect"
            sensor.quality_flag_until = datetime.now(UTC) + timedelta(hours=SENSOR_FLAG_HOURS)
            self.session.flush()

        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=explanation_id,
            action="feedback",
            after={"verdict": data.verdict, "suspect_sensor_id": str(data.suspect_sensor_id or "")},
        )
        self.session.commit()
        return feedback


class QualityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = QualityMetricRepository(session)
        self.narrations = NarrationRepository(session)

    def for_model(self, model_id: uuid.UUID) -> dict[str, Any]:
        pass_rate, count = self.narrations.pass_rate(model_id)
        return {
            "model_id": model_id,
            "metrics": self.repo.for_model(model_id),
            "narration_audit_pass_rate": pass_rate,
            "narration_audit_count": count,
            "llm_enabled": bool(get_settings().llm_endpoint),
        }

    def audits(self, model_id: uuid.UUID | None, passed: bool | None, limit: int) -> list[dict[str, Any]]:
        rows = self.narrations.audits(model_id=model_id, passed=passed, limit=limit)
        return [
            {
                "audit": audit,
                "kind": narration.kind,
                "lang": narration.lang,
                "final_text": narration.final_text,
                "used_llm": narration.final_text == narration.llm_text,
            }
            for audit, narration in rows
        ]

    def model_or_404(self, model_id: uuid.UUID) -> Any:
        from app.modules.pdm.models import Model

        model = self.session.get(Model, model_id)
        if model is None:
            raise NotFoundError(f"Model {model_id} not found")
        return model

    def global_importance(self, model_id: uuid.UUID) -> dict[str, Any]:
        """Written by the insights task (after training, hourly, or on demand) into the model's hyperparams."""
        model = self.model_or_404(model_id)
        stored = (model.hyperparams or {}).get("global_importance") or {}
        features = sorted(
            ({"feature": name, "importance": float(value)} for name, value in stored.items()),
            key=lambda row: row["importance"],
            reverse=True,
        )
        return {
            "model_id": model_id,
            "method": "mean_abs_shap",
            "features": features,
            "partial_dependence": (model.hyperparams or {}).get("partial_dependence") or {},
        }
