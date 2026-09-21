"""Synthetic dataset loader — reads Parquet exports from the simulator."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_EXPORT_DIR = Path("/data/synthetic")


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


def load_cmapss(data_dir: Path | str, subset: str = "FD001") -> dict[str, pd.DataFrame]:
    """Load a C-MAPSS subset into train/test DataFrames.

    Expected files: ``train_{subset}.txt``, ``test_{subset}.txt``, ``RUL_{subset}.txt``
    """
    data_dir = Path(data_dir)
    cols = ["unit_id", "cycle"] + [f"setting_{i}" for i in range(1, 4)] + [f"s_{i}" for i in range(1, 22)]

    train_path = data_dir / f"train_{subset}.txt"
    test_path = data_dir / f"test_{subset}.txt"
    rul_path = data_dir / f"RUL_{subset}.txt"

    if not train_path.exists():
        raise FileNotFoundError(f"C-MAPSS file not found: {train_path}")

    train_df = pd.read_csv(train_path, sep=r"\s+", header=None, names=cols)
    test_df = pd.read_csv(test_path, sep=r"\s+", header=None, names=cols) if test_path.exists() else pd.DataFrame()

    # Compute RUL for training data
    max_cycles = train_df.groupby("unit_id")["cycle"].max().reset_index().rename(columns={"cycle": "max_cycle"})
    train_df = train_df.merge(max_cycles, on="unit_id")
    train_df["rul"] = train_df["max_cycle"] - train_df["cycle"]
    train_df = train_df.drop(columns=["max_cycle"])

    result: dict[str, pd.DataFrame] = {"train": train_df}
    if not test_df.empty:
        result["test"] = test_df
    if rul_path.exists():
        result["rul"] = pd.read_csv(rul_path, header=None, names=["rul"])

    return result
