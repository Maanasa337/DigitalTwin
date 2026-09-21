"""Feature -> human label, unit and actionable range, loaded from feature_labels.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DEFAULT_LABELS_PATH = Path(__file__).with_name("feature_labels.yaml")


@dataclass(frozen=True)
class FeatureLabel:
    name: str
    label: str
    unit: str
    higher_is: str = "worse"
    actionable: bool = False
    min: float | None = None
    max: float | None = None
    step: float | None = None

    def direction_word(self, contribution: float) -> str:
        """How this feature's contribution reads to a human: pushing the prediction up or down."""
        if contribution == 0:
            return "neutral"
        return "raising" if contribution > 0 else "lowering"


class FeatureLabels:
    """Resolves a raw feature name (possibly with a windowed-statistic suffix) to a FeatureLabel."""

    def __init__(self, features: dict[str, dict[str, Any]], suffixes: dict[str, str]) -> None:
        self._features = features
        self._suffixes = suffixes

    def get(self, name: str) -> FeatureLabel:
        base, suffix_word = self._split_suffix(name)
        spec = self._features.get(base, {})
        label = spec.get("label", base.replace("_", " ").replace(".", " ").strip().capitalize())
        if suffix_word:
            label = f"{label} {suffix_word}"
        return FeatureLabel(
            name=name,
            label=label,
            unit=str(spec.get("unit", "")),
            higher_is=spec.get("higher_is", "worse"),
            # A derived statistic is not something an operator can dial in, only the raw setpoint is.
            actionable=bool(spec.get("actionable", False)) and suffix_word is None,
            min=spec.get("min"),
            max=spec.get("max"),
            step=spec.get("step"),
        )

    def actionable(self) -> list[FeatureLabel]:
        return [self.get(name) for name, spec in self._features.items() if spec.get("actionable")]

    def vocabulary(self) -> set[str]:
        """Every label word an audited narration is allowed to attribute a prediction to."""
        words: set[str] = set()
        for name in self._features:
            words.add(self.get(name).label.lower())
        return words

    def _split_suffix(self, name: str) -> tuple[str, str | None]:
        # A feature named in the YAML wins outright: 'spindle.vib_rms' is a sensor, not the RMS
        # statistic of a 'spindle.vib' that does not exist.
        if name in self._features:
            return name, None
        for suffix, word in self._suffixes.items():
            if name.endswith(suffix) and name[: -len(suffix)] in self._features:
                return name[: -len(suffix)], word
        for suffix, word in self._suffixes.items():
            if name.endswith(suffix):
                return name[: -len(suffix)], word
        return name, None


@lru_cache
def load_labels(path: str | None = None) -> FeatureLabels:
    doc = yaml.safe_load(Path(path or DEFAULT_LABELS_PATH).read_text(encoding="utf-8")) or {}
    return FeatureLabels(doc.get("features") or {}, doc.get("suffixes") or {})
