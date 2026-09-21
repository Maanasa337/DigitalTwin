"""Narration audit (FR-XAI-07).

An LLM paraphrase is only shown to a user if it still says what the attributions say. Every check
here is a reason to fall back to the template, which is why each one is recorded separately rather
than collapsing to a single boolean.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from twinvoice_xai.attribution import Attribution
from twinvoice_xai.labels import FeatureLabels, load_labels

RANK_AGREEMENT_MIN = 2 / 3  # at least 2 of the top 3 drivers must survive the paraphrase
SIGN_AGREEMENT_MIN = 1.0  # a flipped direction is always a failure: it reverses the advice
NUMERIC_TOLERANCE = 0.05

_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")
_RAISE_WORDS = ("raising", "increasing", "rising", "pushing up", "driving up", "higher", "elevated")
_LOWER_WORDS = ("lowering", "decreasing", "falling", "pushing down", "driving down", "reducing", "lower")


@dataclass(frozen=True)
class AuditResult:
    rank_agreement: float
    sign_agreement: float
    numeric_within_tolerance: bool
    hallucinated_features: list[str] = field(default_factory=list)
    unsupported_recommendation: bool = False
    passed: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_narration(
    text: str,
    attributions: list[Attribution],
    *,
    allowed_numbers: list[float] | None = None,
    recommended_actions: list[str] | None = None,
    labels: FeatureLabels | None = None,
    top_k: int = 3,
) -> AuditResult:
    """Check a narration against the explanation it claims to describe."""
    labels = labels or load_labels()
    lowered = text.lower()
    top = attributions[:top_k]

    mentioned = [a for a in top if a.label.lower() in lowered]
    rank_agreement = len(mentioned) / len(top) if top else 1.0

    sign_ok = [_sign_matches(lowered, a) for a in mentioned]
    sign_agreement = sum(sign_ok) / len(sign_ok) if sign_ok else 1.0

    numbers = _numbers_in(text)
    expected = list(allowed_numbers or []) + [round(a.value, 4) for a in attributions]
    unmatched = [n for n in numbers if not _close_to_any(n, expected)]

    hallucinated = _hallucinated_features(lowered, attributions, labels)
    unsupported = _unsupported_recommendation(lowered, recommended_actions or [])

    passed = (
        rank_agreement >= RANK_AGREEMENT_MIN
        and sign_agreement >= SIGN_AGREEMENT_MIN
        and not unmatched
        and not hallucinated
        and not unsupported
    )
    return AuditResult(
        rank_agreement=round(rank_agreement, 4),
        sign_agreement=round(sign_agreement, 4),
        numeric_within_tolerance=not unmatched,
        hallucinated_features=hallucinated,
        unsupported_recommendation=unsupported,
        passed=passed,
        details={
            "mentioned_top_features": [a.feature for a in mentioned],
            "expected_top_features": [a.feature for a in top],
            "unmatched_numbers": unmatched,
        },
    )


def _sign_matches(lowered: str, attribution: Attribution) -> bool:
    """The claim near a feature's label must not contradict the sign of its contribution."""
    position = lowered.find(attribution.label.lower())
    window = lowered[max(0, position - 80) : position + 160]
    says_up = any(word in window for word in _RAISE_WORDS)
    says_down = any(word in window for word in _LOWER_WORDS)
    if says_up == says_down:  # says both or says neither: nothing to contradict
        return True
    return says_up if attribution.direction == "raising" else says_down


def _numbers_in(text: str) -> list[float]:
    out: list[float] = []
    for match in _NUMBER.findall(text):
        try:
            out.append(float(match.replace(",", "")))
        except ValueError:
            continue
    return out


def _close_to_any(value: float, expected: list[float]) -> bool:
    for candidate in expected:
        if candidate == 0:
            if abs(value) < 1e-9:
                return True
            continue
        if abs(value - candidate) / abs(candidate) <= NUMERIC_TOLERANCE:
            return True
    return False


def _hallucinated_features(lowered: str, attributions: list[Attribution], labels: FeatureLabels) -> list[str]:
    """Feature labels the narration invokes that this explanation never attributed anything to."""
    present = {a.label.lower() for a in attributions}
    return sorted({word for word in labels.vocabulary() if word in lowered and word not in present})


def _unsupported_recommendation(lowered: str, recommended_actions: list[str]) -> bool:
    """A narration may only recommend what the reason card recommends."""
    imperatives = ("replace", "shut down", "stop the", "order ", "dismantle", "rebuild", "overhaul")
    if not any(word in lowered for word in imperatives):
        return False
    supported = " ".join(recommended_actions).lower()
    return not any(word in supported for word in imperatives if word in lowered)


def pass_rate(results: list[AuditResult]) -> float:
    return sum(r.passed for r in results) / len(results) if results else 1.0
