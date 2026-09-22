"""Per-asset rolling sample buffer that turns the MQTT stream into the model's feature vector.

Features come from `twinvoice_pdm.features.build_features` with the bundle's own `FeatureSpec`, the
same function the trainer used, so the edge and the platform cannot compute a feature differently.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

import numpy as np
import pandas as pd
from twinvoice_pdm.features import FeatureSpec, build_features


class RollingWindow:
    """The last ``window_size`` samples of one asset, emitting a feature vector every ``stride``."""

    def __init__(self, spec: FeatureSpec, feature_names: list[str]) -> None:
        self.spec = spec
        self.feature_names = feature_names
        self._rows: deque[tuple[datetime, dict[str, float]]] = deque(maxlen=spec.window_size)
        self._last: dict[str, float] = {}
        self._since_emit = 0

    def add(self, time: datetime, metrics: dict[str, float | None]) -> bool:
        """Append one sample; True when a full window is due for scoring.

        A DDATA carries only the metrics that changed and may mark a reading bad (None), so each
        sample carries every sensor forward from its last good value.
        """
        for name in self.spec.sensor_cols:
            value = metrics.get(name)
            if value is not None:
                self._last[name] = float(value)
        if not any(name in self._last for name in self.spec.sensor_cols):
            return False
        self._rows.append((time, {name: self._last.get(name, 0.0) for name in self.spec.sensor_cols}))
        self._since_emit += 1
        if len(self._rows) == self.spec.window_size and self._since_emit >= self.spec.stride:
            self._since_emit = 0
            return True
        return False

    @property
    def span(self) -> tuple[datetime, datetime]:
        return self._rows[0][0], self._rows[-1][0]

    def vector(self) -> np.ndarray:
        """The current window's features, ordered as the model expects."""
        frame = pd.DataFrame([row for _, row in self._rows], columns=self.spec.sensor_cols)
        spec = FeatureSpec(
            window_size=self.spec.window_size,
            stride=self.spec.window_size,
            stat_features=self.spec.stat_features,
            sensor_cols=self.spec.sensor_cols,
        )
        features = build_features(frame, spec, group_col=None)
        row = features.iloc[-1]
        return np.array([float(row.get(name, 0.0)) for name in self.feature_names], dtype=np.float64)
