"""Dataset loaders: simulator Parquet exports and the public PdM benchmarks (C-MAPSS, AI4I 2020, MetroPT-3)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_EXPORT_DIR = Path("/data/synthetic")

# Where `data/download.py` extracts C-MAPSS inside data/raw/cmapss; the zip nests one folder deep.
CMAPSS_SUBDIR = "6. Turbofan Engine Degradation Simulation Data Set"
CMAPSS_SETTINGS = ["setting_1", "setting_2", "setting_3"]
CMAPSS_SENSORS = [f"s_{i}" for i in range(1, 22)]

AI4I_FILE = "ai4i2020.csv"
AI4I_TARGET = "machine_failure"
# The five failure-type flags are the label broken down; feeding them to a model is target leakage.
AI4I_LEAKAGE = ["TWF", "HDF", "PWF", "OSF", "RNF", "UDI", "Product ID"]
AI4I_RENAME = {
    "Air temperature [K]": "air_temp_k",
    "Process temperature [K]": "process_temp_k",
    "Rotational speed [rpm]": "rot_speed_rpm",
    "Torque [Nm]": "torque_nm",
    "Tool wear [min]": "tool_wear_min",
    "Machine failure": AI4I_TARGET,
}

METROPT3_FILE = "MetroPT3(AirCompressor).csv"
METROPT3_ANALOG = ["TP2", "TP3", "H1", "DV_pressure", "Reservoirs", "Oil_temperature", "Motor_current"]
METROPT3_DIGITAL = ["COMP", "DV_eletric", "Towers", "MPG", "LPS", "Pressure_switch", "Oil_level", "Caudal_impulses"]


@dataclass(frozen=True)
class FailureWindow:
    start: pd.Timestamp
    end: pd.Timestamp
    kind: str


# The company's failure reports, from the table in `Data Description_Metro.pdf` shipped with the
# UCI archive (checked against data/raw/metropt3). The PDF labels all four as air leaks; Veloso et
# al. 2022 (Scientific Data 9:764) describe #4 as an oil leak. The timestamps agree in both sources.
METROPT3_FAILURES: tuple[FailureWindow, ...] = (
    FailureWindow(pd.Timestamp("2020-04-18 00:00"), pd.Timestamp("2020-04-18 23:59"), "air_leak"),
    FailureWindow(pd.Timestamp("2020-05-29 23:30"), pd.Timestamp("2020-05-30 06:00"), "air_leak"),
    FailureWindow(pd.Timestamp("2020-06-05 10:00"), pd.Timestamp("2020-06-07 14:30"), "air_leak"),
    FailureWindow(pd.Timestamp("2020-07-15 14:30"), pd.Timestamp("2020-07-15 19:00"), "air_leak"),
)


def load_synthetic(
    export_dir: Path | str = DEFAULT_EXPORT_DIR,
    asset_code: str | None = None,
) -> pd.DataFrame:
    """Load simulator Parquet exports into a single DataFrame.

    If asset_code is given, filters to that asset only.
    """
    export_dir = Path(export_dir)
    if not export_dir.exists():
        raise FileNotFoundError(f"Export directory not found: {export_dir}")

    parquet_files = sorted(export_dir.glob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"No Parquet files found in {export_dir}")

    frames = []
    for f in parquet_files:
        df = pd.read_parquet(f)
        if asset_code and "asset_code" in df.columns:
            df = df[df["asset_code"] == asset_code]
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    if "time" in combined.columns or "timestamp" in combined.columns:
        time_col = "time" if "time" in combined.columns else "timestamp"
        combined = combined.sort_values(time_col).reset_index(drop=True)

    return combined


def cmapss_dir(raw_dir: Path | str) -> Path:
    """The folder holding the C-MAPSS text files, given data/raw or data/raw/cmapss or the folder itself."""
    raw_dir = Path(raw_dir)
    for candidate in (raw_dir, raw_dir / CMAPSS_SUBDIR, raw_dir / "cmapss" / CMAPSS_SUBDIR, raw_dir / "cmapss"):
        if (candidate / "train_FD001.txt").exists():
            return candidate
    raise FileNotFoundError(f"C-MAPSS not found under {raw_dir}; run `python data/download.py cmapss`")


def load_cmapss(data_dir: Path | str, subset: str = "FD001") -> dict[str, pd.DataFrame]:
    """Load a C-MAPSS subset into train/test DataFrames.

    Expected files: ``train_{subset}.txt``, ``test_{subset}.txt``, ``RUL_{subset}.txt``

    Both frames carry a ``rul`` column. Training engines run to failure, so their RUL is counted back
    from the last cycle; test engines stop early, and ``RUL_{subset}.txt`` gives each one's true RUL at
    its last recorded cycle, from which every earlier cycle's RUL follows.
    """
    data_dir = Path(data_dir)
    cols = ["unit_id", "cycle", *CMAPSS_SETTINGS, *CMAPSS_SENSORS]

    train_path = data_dir / f"train_{subset}.txt"
    test_path = data_dir / f"test_{subset}.txt"
    rul_path = data_dir / f"RUL_{subset}.txt"

    if not train_path.exists():
        raise FileNotFoundError(f"C-MAPSS file not found: {train_path}")

    train_df = pd.read_csv(train_path, sep=r"\s+", header=None, names=cols)
    test_df = pd.read_csv(test_path, sep=r"\s+", header=None, names=cols) if test_path.exists() else pd.DataFrame()
    train_df["rul"] = train_df.groupby("unit_id")["cycle"].transform("max") - train_df["cycle"]

    result: dict[str, pd.DataFrame] = {"train": train_df}
    if rul_path.exists():
        rul_df = pd.read_csv(rul_path, header=None, names=["rul"], sep=r"\s+")
        result["rul"] = rul_df
        if not test_df.empty:
            # Row i of RUL_FD00x.txt belongs to test unit i + 1.
            final_rul = pd.Series(rul_df["rul"].to_numpy(), index=np.arange(1, len(rul_df) + 1))
            last_cycle = test_df.groupby("unit_id")["cycle"].transform("max")
            test_df["rul"] = test_df["unit_id"].map(final_rul) + (last_cycle - test_df["cycle"])
    if not test_df.empty:
        result["test"] = test_df

    return result


def normalise_operating_conditions(
    train: pd.DataFrame,
    others: list[pd.DataFrame],
    sensor_cols: list[str],
    *,
    n_conditions: int = 6,
    seed: int = 42,
) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    """Z-score each sensor within its operating condition (FD002/FD004 fly six regimes).

    The regime moves a sensor far more than wear does, so raw values mostly encode altitude and
    throttle. KMeans on the three settings recovers the regimes; mean and std are fitted on the
    training frame only and applied unchanged to the others, so the test set leaks nothing back.
    """
    from sklearn.cluster import KMeans

    kmeans = KMeans(n_clusters=n_conditions, n_init=10, random_state=seed)
    train = train.copy()
    train["condition"] = kmeans.fit_predict(train[CMAPSS_SETTINGS].round(2).to_numpy())
    stats = train.groupby("condition")[sensor_cols].agg(["mean", "std"])

    def apply(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        if "condition" not in frame.columns:
            frame["condition"] = kmeans.predict(frame[CMAPSS_SETTINGS].round(2).to_numpy())
        for col in sensor_cols:
            mean = frame["condition"].map(stats[(col, "mean")])
            std = frame["condition"].map(stats[(col, "std")]).replace(0.0, 1.0).fillna(1.0)
            frame[col] = (frame[col] - mean) / std
        return frame

    return apply(train), [apply(o) for o in others]


def load_ai4i(path: Path | str) -> pd.DataFrame:
    """AI4I 2020 as model-ready columns plus the binary ``machine_failure`` target.

    Accepts the CSV itself or the folder holding it. The file starts with a UTF-8 BOM, which would
    otherwise glue itself onto the first column name.
    """
    path = Path(path)
    if path.is_dir():
        path = path / AI4I_FILE
    if not path.exists():
        raise FileNotFoundError(f"AI4I file not found: {path}; run `python data/download.py ai4i`")
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.drop(columns=[c for c in AI4I_LEAKAGE if c in df.columns]).rename(columns=AI4I_RENAME)
    type_dummies = pd.get_dummies(df.pop("Type"), prefix="type", dtype=float)
    df = pd.concat([df, type_dummies], axis=1)
    # Two physically meaningful interactions from the dataset's own failure definitions
    # (power = torque x speed, heat dissipation = process - air temperature).
    df["power_w"] = df["torque_nm"] * df["rot_speed_rpm"] * 2 * np.pi / 60
    df["temp_delta_k"] = df["process_temp_k"] - df["air_temp_k"]
    return df


def load_metropt3(path: Path | str, *, resample: str = "1min", nrows: int | None = None) -> pd.DataFrame:
    """MetroPT-3, resampled to ``resample`` means, indexed by timestamp.

    The raw log is ~15 M rows at up to 1 Hz (about 200 MB); a one-minute mean keeps the leak
    signatures, which build over hours, and makes the frame small enough to model. Gaps where the
    train was out of service stay as missing minutes rather than being interpolated across.
    """
    path = Path(path)
    if path.is_dir():
        path = path / METROPT3_FILE
    if not path.exists():
        raise FileNotFoundError(f"MetroPT-3 file not found: {path}; run `python data/download.py metropt3`")
    columns = ["timestamp", *METROPT3_ANALOG, *METROPT3_DIGITAL]
    try:
        # pyarrow (installed with mlflow) parses the 200 MB file several times faster than the C engine.
        df = (
            pd.read_csv(path, usecols=columns, engine="pyarrow")
            if nrows is None
            else pd.read_csv(path, usecols=columns, nrows=nrows)
        )
    except (ImportError, ValueError):
        df = pd.read_csv(path, usecols=columns, nrows=nrows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    return df.resample(resample).mean().dropna(how="all")


def metropt3_labels(index: pd.DatetimeIndex) -> np.ndarray:
    """1 where a timestamp falls inside a reported failure window, else 0."""
    labels = np.zeros(len(index), dtype=int)
    for window in METROPT3_FAILURES:
        labels[(index >= window.start) & (index <= window.end)] = 1
    return labels


def dataset_sha(raw_dir: Path | str, name: str) -> str | None:
    """The archive sha256 `data/download.py` wrote to `<name>/.complete`, if the dataset is present."""
    marker = Path(raw_dir) / name / ".complete"
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip() or None
    return None


def frame_hash(df: pd.DataFrame) -> str:
    """A short content hash of a DataFrame, recorded as a model's dataset_hash."""
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes()).hexdigest()[:16]
