"""Reason card (FR-XAI-05): predicted failure mode + top attributions -> symptom / cause / action."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from twinvoice_xai.attribution import Attribution

KB_DIR = Path(__file__).with_name("knowledge_base")


@dataclass(frozen=True)
class KbEntry:
    code: str
    symptom: str
    likely_cause: str
    recommended_action: str
    evidence_metrics: list[str] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)
    est_duration_min: int | None = None


@dataclass(frozen=True)
class ReasonCard:
    symptom: str
    evidence: list[dict[str, Any]]
    likely_cause: str
    action: str
    confidence: float
    failure_mode: str
    parts: list[str] = field(default_factory=list)
    est_duration_min: int | None = None
    kb_entry_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@lru_cache
def load_kb(lang: str = "en") -> dict[str, KbEntry]:
    path = KB_DIR / f"{lang}.yaml"
    if not path.exists():
        path = KB_DIR / "en.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        code: KbEntry(
            code=code,
            symptom=spec["symptom"],
            likely_cause=spec["likely_cause"],
            recommended_action=spec["recommended_action"],
            evidence_metrics=list(spec.get("evidence_metrics") or []),
            parts=list(spec.get("parts") or []),
            est_duration_min=spec.get("est_duration_min"),
        )
        for code, spec in doc.items()
    }


def build_reason_card(
    failure_mode: str,
    attributions: list[Attribution],
    *,
    mode_probability: float | None = None,
    lang: str = "en",
    top_k: int = 5,
    kb_entry_id: str | None = None,
) -> ReasonCard | None:
    """Match the predicted mode against the KB and corroborate it with the attributions that fired.

    Returns None for an unknown mode rather than inventing advice: a made-up recommended action is
    worse than no card at all, because a technician would act on it.
    """
    entry = load_kb(lang).get(failure_mode)
    if entry is None:
        return None

    top = attributions[:top_k]
    evidence = [
        {
            "feature": a.feature,
            "label": a.label,
            "value": round(a.value, 4),
            "unit": a.unit,
            "direction": a.direction,
            "share": round(a.share, 4),
            "supports_mode": _supports(a.feature, entry.evidence_metrics),
        }
        for a in top
    ]
    return ReasonCard(
        symptom=entry.symptom,
        evidence=evidence,
        likely_cause=entry.likely_cause,
        action=entry.recommended_action,
        confidence=_confidence(evidence, entry, mode_probability),
        failure_mode=failure_mode,
        parts=entry.parts,
        est_duration_min=entry.est_duration_min,
        kb_entry_id=kb_entry_id,
    )


def _supports(feature: str, evidence_metrics: list[str]) -> bool:
    return any(feature == metric or feature.startswith(f"{metric}_") for metric in evidence_metrics)


def _confidence(evidence: list[dict[str, Any]], entry: KbEntry, mode_probability: float | None) -> float:
    """Blend how well the evidence matches the mode's signature with the classifier's own probability."""
    if not entry.evidence_metrics:
        return round(mode_probability if mode_probability is not None else 1.0, 4)

    matched_share = sum(e["share"] for e in evidence if e["supports_mode"])
    if mode_probability is None:
        return round(min(1.0, matched_share), 4)
    return round(min(1.0, 0.5 * mode_probability + 0.5 * matched_share), 4)
