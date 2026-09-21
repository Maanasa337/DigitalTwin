"""Counterfactuals (FR-XAI-06): the smallest actionable change that reaches a target outcome.

Only features marked `actionable` in feature_labels.yaml are varied, and only inside their declared
range — a counterfactual that says "run the bearing 10 °C cooler" is useless if nobody can do it.

Deliberately a constrained coordinate search rather than DiCE: the actionable set is four features on
a quantised grid, which a direct search covers exhaustively enough and keeps the dependency out.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from twinvoice_xai.labels import FeatureLabel, FeatureLabels, load_labels


@dataclass(frozen=True)
class Change:
    feature: str
    label: str
    unit: str
    from_: float
    to: float
    actionable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "label": self.label,
            "unit": self.unit,
            "from": round(self.from_, 4),
            "to": round(self.to, 4),
            "actionable": self.actionable,
        }


@dataclass(frozen=True)
class CounterfactualResult:
    target: str
    changes: list[Change]
    outcome: dict[str, float]
    feasibility_score: float
    action_text: str = ""
    found: bool = True

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["changes"] = [c.to_dict() for c in self.changes]
        return out


def search_counterfactual(
    predict: Callable[[np.ndarray], float],
    x: np.ndarray,
    feature_names: list[str],
    *,
    target: str,
    satisfied: Callable[[float], bool],
    labels: FeatureLabels | None = None,
    max_features_changed: int = 2,
    outcome_key: str = "rul_point",
) -> CounterfactualResult:
    """Find the cheapest change set that makes `satisfied(predict(x'))` true.

    Cost is the sum of per-feature relative moves, so one large adjustment loses to two small ones
    only when the total displacement is genuinely smaller — which is what an operator would prefer.
    """
    labels = labels or load_labels()
    x = np.asarray(x, dtype=float).reshape(-1)
    index = {name: i for i, name in enumerate(feature_names)}
    candidates = [label for label in labels.actionable() if label.name in index]

    if not candidates:
        return CounterfactualResult(
            target=target, changes=[], outcome={}, feasibility_score=0.0, action_text="", found=False
        )

    best: tuple[float, list[Change], float] | None = None
    for size in range(1, max_features_changed + 1):
        for combo in itertools.combinations(candidates, size):
            grids = [_grid(label, x[index[label.name]]) for label in combo]
            for point in itertools.product(*grids):
                probe = x.copy()
                for label, value in zip(combo, point, strict=True):
                    probe[index[label.name]] = value
                prediction = float(predict(probe.reshape(1, -1)))
                if not satisfied(prediction):
                    continue
                cost = sum(
                    _relative_move(label, x[index[label.name]], value)
                    for label, value in zip(combo, point, strict=True)
                )
                if best is None or cost < best[0]:
                    best = (
                        cost,
                        [
                            Change(
                                feature=label.name,
                                label=label.label,
                                unit=label.unit,
                                from_=float(x[index[label.name]]),
                                to=float(value),
                                actionable=True,
                            )
                            for label, value in zip(combo, point, strict=True)
                            if value != x[index[label.name]]
                        ],
                        prediction,
                    )
        if best is not None:
            # A smaller change set already works; widening it can only add unnecessary interventions.
            break

    if best is None:
        return CounterfactualResult(
            target=target, changes=[], outcome={}, feasibility_score=0.0, action_text="", found=False
        )

    cost, changes, prediction = best
    return CounterfactualResult(
        target=target,
        changes=changes,
        outcome={outcome_key: round(prediction, 4)},
        feasibility_score=round(1.0 / (1.0 + cost), 4),
        action_text=action_text(changes),
        found=True,
    )


def action_text(changes: list[Change]) -> str:
    if not changes:
        return "No change needed."
    parts = [
        f"{c.label} from {c.from_:g} to {c.to:g}{(' ' + c.unit) if c.unit else ''}"
        for c in changes
    ]
    return "Adjust " + " and ".join(parts) + "."


def _grid(label: FeatureLabel, current: float) -> list[float]:
    low = label.min if label.min is not None else current * 0.5
    high = label.max if label.max is not None else current * 1.5
    step = label.step or max((high - low) / 10.0, 1e-6)
    n = round((high - low) / step) + 1
    return [round(low + i * step, 6) for i in range(max(n, 2))]


def _relative_move(label: FeatureLabel, current: float, value: float) -> float:
    """Displacement as a fraction of the feature's own range, so units cannot skew the comparison."""
    span = (label.max - label.min) if (label.max is not None and label.min is not None) else abs(current) or 1.0
    return abs(value - current) / (span or 1.0)
