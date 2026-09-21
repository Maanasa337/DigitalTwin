"""Feature extraction: sliding windows, statistical features, spectral features."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureSpec:
    """Defines which features to extract and how."""
    window_size: int = 60
    stride: int = 10
    stat_features: list[str] = field(default_factory=lambda: ["mean", "std", "min", "max", "slope", "rms", "kurtosis"])
    sensor_cols: list[str] = field(default_factory=list)


def rolling_windows(arr: np.ndarray, window_size: int, stride: int) -> np.ndarray:
    """Create sliding windows from a 1D or 2D array."""
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    n_samples, n_features = arr.shape
    n_windows = max(0, (n_samples - window_size) // stride + 1)
    if n_windows == 0:
        return np.empty((0, window_size, n_features))
    indices = np.arange(n_windows) * stride
    windows = np.array([arr[i : i + window_size] for i in indices])
    return windows


def compute_stats(window: np.ndarray) -> dict[str, float]:
    """Compute statistical features for a single 1D window."""
    n = len(window)
    if n == 0:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "slope": 0.0, "rms": 0.0, "kurtosis": 0.0}

    mean = float(np.mean(window))
    std = float(np.std(window, ddof=0))
    rms = float(np.sqrt(np.mean(window ** 2)))
    slope = _ols_slope(window)
    kurt = _kurtosis(window, mean, std)

    return {
        "mean": mean,
        "std": std,
        "min": float(np.min(window)),
        "max": float(np.max(window)),
        "slope": slope,
        "rms": rms,
        "kurtosis": kurt,
    }


def _ols_slope(window: np.ndarray) -> float:
    """Ordinary least squares slope (trend indicator)."""
    n = len(window)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=np.float64)
    x_mean = (n - 1) / 2.0
    numerator = np.sum((x - x_mean) * (window - np.mean(window)))
    denominator = np.sum((x - x_mean) ** 2)
    return float(numerator / denominator) if denominator > 0 else 0.0


def _kurtosis(window: np.ndarray, mean: float, std: float) -> float:
    """Excess kurtosis (Fisher's definition)."""
    if std < 1e-10 or len(window) < 4:
        return 0.0
    return float(np.mean(((window - mean) / std) ** 4) - 3.0)


def build_features(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    """Extract sliding-window statistical features from a multi-column DataFrame.

    Each row in the output represents one window, with columns like
    ``{sensor}_{stat}`` (e.g. ``vib_rms_mean``, ``temp_std``).
    """
    sensor_cols = spec.sensor_cols or [c for c in df.columns if c not in ("time", "timestamp", "unit_id", "cycle")]
    arr = df[sensor_cols].values.astype(np.float64)
    windows = rolling_windows(arr, spec.window_size, spec.stride)

    if windows.shape[0] == 0:
        return pd.DataFrame()

    rows: list[dict[str, float]] = []
    for w_idx in range(windows.shape[0]):
        row: dict[str, float] = {}
        for s_idx, sensor in enumerate(sensor_cols):
            stats = compute_stats(windows[w_idx, :, s_idx])
            for stat_name in spec.stat_features:
                if stat_name in stats:
                    row[f"{sensor}_{stat_name}"] = stats[stat_name]
        rows.append(row)

    return pd.DataFrame(rows)
