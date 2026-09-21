"""Confidence (FR-XAI-11): why a prediction should or should not be trusted, in words.

Four independent things can undermine a prediction — a wide interval, the two models disagreeing,
a sensor that is stuck or missing, and inputs outside the training manifold. Each is reported as its
own reason so the operator learns which one to fix.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

WIDE_INTERVAL_RATIO = 0.6
VERY_WIDE_INTERVAL_RATIO = 1.2
OOD_THRESHOLD = 3.0


@dataclass(frozen=True)
class ConfidenceResult:
    label: str
    reasons: list[str] = field(default_factory=list)
    score: float = 1.0
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def interval_width_ratio(point: float | None, low: float | None, high: float | None) -> float | None:
    """(high - low) / point. None when there is no interval, or when point is 0 and the ratio is undefined."""
    if point is None or low is None or high is None or point == 0:
        return None
    return abs(high - low) / abs(point)


def assess_confidence(
    *,
    rul_point: float | None = None,
    rul_low: float | None = None,
    rul_high: float | None = None,
    model_agreement: float | None = None,
    degraded_sensors: list[str] | None = None,
    drift_flag: bool = False,
    ood_score: float | None = None,
) -> ConfidenceResult:
    """Combine the four signals into a label plus the reasons behind it."""
    reasons: list[str] = []
    penalty = 0.0
    signals: dict[str, Any] = {}

    ratio = interval_width_ratio(rul_point, rul_low, rul_high)
    signals["interval_width_ratio"] = round(ratio, 4) if ratio is not None else None
    if ratio is not None and ratio >= VERY_WIDE_INTERVAL_RATIO:
        reasons.append(f"Prediction interval is very wide ({ratio:.0%} of the estimate)")
        penalty += 0.5
    elif ratio is not None and ratio >= WIDE_INTERVAL_RATIO:
        reasons.append(f"Prediction interval is wide ({ratio:.0%} of the estimate)")
        penalty += 0.25

    signals["model_agreement"] = model_agreement
    if model_agreement is not None and model_agreement < 0.34:
        reasons.append("The glass-box model highlights different drivers than the production model")
        penalty += 0.3

    degraded = list(degraded_sensors or [])
    signals["degraded_sensors"] = degraded
    if degraded:
        reasons.append(f"Sensor data quality is degraded: {', '.join(degraded)}")
        penalty += 0.25 * min(len(degraded), 2)

    signals["drift_flag"] = drift_flag
    if drift_flag:
        reasons.append("Input distribution has drifted from the training data")
        penalty += 0.3

    signals["ood_score"] = ood_score
    if ood_score is not None and ood_score > OOD_THRESHOLD:
        reasons.append("Current readings are outside the range the model was trained on")
        penalty += 0.3

    score = max(0.0, 1.0 - penalty)
    if not reasons:
        reasons.append("Interval is tight, models agree, and all sensors are reporting normally")
    return ConfidenceResult(label=_label(score), reasons=reasons, score=round(score, 4), signals=signals)


def _label(score: float) -> str:
    if score >= 0.7:
        return "high"
    return "medium" if score >= 0.4 else "low"
