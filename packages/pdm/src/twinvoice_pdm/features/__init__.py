"""Feature extraction: sliding windows, statistical features, spectral features."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

# Columns that identify or time a row; they are never sensors, whatever their dtype.
NON_SENSOR_COLS = frozenset({"time", "timestamp", "unit_id", "cycle", "asset_code", "asset_id"})
STAT_NAMES = ("mean", "std", "min", "max", "slope", "rms", "kurtosis", "last")


@dataclass(frozen=True)
class FeatureSpec:
    """Defines which features to extract and how."""
    window_size: int = 60
    stride: int = 10
    stat_features: list[str] = field(default_factory=lambda: ["mean", "std", "min", "max", "slope", "rms", "kurtosis"])
    sensor_cols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureSpec:
        return cls(
            window_size=int(data.get("window_size", 60)),
            stride=int(data.get("stride", 10)),
            stat_features=list(data.get("stat_features") or cls().stat_features),
            sensor_cols=list(data.get("sensor_cols") or []),
        )


def rolling_windows(arr: np.ndarray, window_size: int, stride: int) -> np.ndarray:
    """Create sliding windows from a 1D or 2D array, shaped (n_windows, window_size, n_features)."""
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    n_samples, n_features = arr.shape
    if n_samples < window_size:
        return np.empty((0, window_size, n_features))
    # A view, not a copy: (n, f) -> (n - w + 1, f, w), then every `stride`-th start.
    view = sliding_window_view(arr, window_size, axis=0)[::stride]
    return np.ascontiguousarray(view.transpose(0, 2, 1))


def compute_stats(window: np.ndarray) -> dict[str, float]:
    """Compute statistical features for a single 1D window."""
    n = len(window)
    if n == 0:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "slope": 0.0, "rms": 0.0, "kurtosis": 0.0}
    stats = _window_stats(np.asarray(window, dtype=np.float64).reshape(1, n, 1))
    return {name: float(values[0, 0]) for name, values in stats.items()}


def _window_stats(windows: np.ndarray) -> dict[str, np.ndarray]:
    """Every statistic for a (n_windows, window_size, n_features) block, each shaped (n_windows, n_features).

    Vectorised over windows and sensors at once: the per-window Python loop this replaces dominated
    training time on C-MAPSS, where stride 1 produces tens of thousands of windows.
    """
    n = windows.shape[1]
    mean = windows.mean(axis=1)
    centred = windows - mean[:, None, :]
    std = np.sqrt((centred**2).mean(axis=1))

    x = np.arange(n, dtype=np.float64) - (n - 1) / 2.0
    denominator = float(np.sum(x**2))
    # sum((x - x̄)(w - w̄)) == sum((x - x̄) w) because the centred x sums to zero.
    slope = np.einsum("t,btf->bf", x, windows) / denominator if denominator > 0 else np.zeros_like(mean)

    safe_std = np.where(std < 1e-10, 1.0, std)
    kurtosis = ((centred / safe_std[:, None, :]) ** 4).mean(axis=1) - 3.0
    # Excess kurtosis is undefined for a flat or very short window; report 0 rather than noise.
    kurtosis = np.where((std < 1e-10) | (n < 4), 0.0, kurtosis)

    return {
        "mean": mean,
        "std": std,
        "min": windows.min(axis=1),
        "max": windows.max(axis=1),
        "slope": slope,
        "rms": np.sqrt((windows**2).mean(axis=1)),
        "kurtosis": kurtosis,
        # The newest reading: on slow-degrading signals it carries information the window mean smears.
        "last": windows[:, -1, :],
    }


def sensor_columns(df: pd.DataFrame, spec: FeatureSpec, group_col: str | None = None) -> list[str]:
    """The sensor columns a spec applies to: explicit, or every numeric non-identifier column."""
    if spec.sensor_cols:
        return list(spec.sensor_cols)
    excluded = NON_SENSOR_COLS | ({group_col} if group_col else set())
    return [c for c in df.columns if c not in excluded and pd.api.types.is_numeric_dtype(df[c])]


def feature_names(sensor_cols: list[str], spec: FeatureSpec) -> list[str]:
    """Output column order of `build_features`: sensor-major, then statistic, `{sensor}_{stat}`."""
    return [f"{sensor}_{stat}" for sensor in sensor_cols for stat in spec.stat_features if stat in STAT_NAMES]


def build_features(df: pd.DataFrame, spec: FeatureSpec, group_col: str | None = "unit_id") -> pd.DataFrame:
    """Extract sliding-window statistical features from a multi-column DataFrame.

    Each row in the output represents one window, with columns like
    ``{sensor}_{stat}`` (e.g. ``vib_rms_mean``, ``temp_std``).

    Windows never cross ``group_col`` boundaries (one C-MAPSS engine's last cycles glued to the next
    engine's first ones is not a window of anything). The output index holds the input index label of
    each window's last row, so callers can join labels such as RUL at the moment the window closes.
    """
    group = group_col if group_col and group_col in df.columns else None
    sensor_cols = sensor_columns(df, spec, group)
    stats = [s for s in spec.stat_features if s in STAT_NAMES]
    columns = feature_names(sensor_cols, spec)

    parts: list[np.ndarray] = []
    ends: list[np.ndarray] = []
    frames = df.groupby(group, sort=False) if group else [(None, df)]
    for _, frame in frames:
        arr = frame[sensor_cols].to_numpy(dtype=np.float64)
        windows = rolling_windows(arr, spec.window_size, spec.stride)
        if windows.shape[0] == 0:
            continue
        computed = _window_stats(windows)
        # (n_windows, n_sensors, n_stats) flattened sensor-major, matching `columns`.
        block = np.stack([computed[s] for s in stats], axis=2).reshape(windows.shape[0], -1)
        parts.append(block)
        end_positions = np.arange(windows.shape[0]) * spec.stride + spec.window_size - 1
        ends.append(frame.index.to_numpy()[end_positions])

    if not parts:
        return pd.DataFrame()

    out = pd.DataFrame(np.vstack(parts), columns=columns, index=np.concatenate(ends))
    out.index.name = "window_end"
    return out
