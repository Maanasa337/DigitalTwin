from pathlib import Path

import pandas as pd
import pytest

from sim.catalog import Catalog
from sim.export import export_run


def test_same_seed_gives_identical_export(catalog: Catalog, tmp_path: Path) -> None:
    kwargs = {"hours": 3.0, "period_s": 60.0, "scenario_code": "demo_day", "seed": 123}
    a = export_run(catalog, out_dir=tmp_path / "a", **kwargs)
    b = export_run(catalog, out_dir=tmp_path / "b", **kwargs)
    c = export_run(catalog, out_dir=tmp_path / "c", **(kwargs | {"seed": 124}))
    df_a, df_b, df_c = (pd.read_parquet(r.path) for r in (a, b, c))
    pd.testing.assert_frame_equal(df_a, df_b)
    assert not df_a.equals(df_c)
    assert a.path.name.startswith("demo_day_seed123_")


def test_export_layout(catalog: Catalog, tmp_path: Path) -> None:
    result = export_run(catalog, hours=1.0, period_s=300.0, out_dir=tmp_path)
    df = pd.read_parquet(result.path)
    assert result.path.name.startswith("baseline_seed42_")
    assert result.rows == len(df) == 12 * 10
    assert list(df.columns) == result.columns
    assert result.columns[:4] == ["time", "asset_code", "asset_type", "state"]
    assert result.columns[-3:] == ["true_rul_h", "driver", "failure_mode"]
    assert {"spindle.vib_rms", "barrel.zone3_temp", "power_kw", "good_count", "damage"} <= set(df)
    assert "damage.spindle" in df and "damage.barrel" in df
    assert str(df["time"].dt.tz) == "UTC"
    assert df["time"].min() == pd.Timestamp("2026-01-05T00:35:00Z")
    press = df[df.asset_code == "press-01"]
    assert press["spindle.vib_rms"].isna().all()
    assert press["damage"].equals(press.filter(like="damage.").max(axis=1))


def test_bearing_failure_true_rul_is_non_increasing_between_resets(
    catalog: Catalog, tmp_path: Path
) -> None:
    result = export_run(
        catalog, hours=12.0, period_s=60.0, scenario_code="bearing_failure_cnc01", out_dir=tmp_path
    )
    cnc = pd.read_parquet(result.path).query("asset_code == 'cnc-01'").reset_index(drop=True)
    entering_maintenance = (cnc["state"] == "MAINTENANCE") & (cnc["state"].shift() != "MAINTENANCE")
    segments = entering_maintenance.cumsum()
    assert segments.max() == 1
    for _, segment in cnc.groupby(segments):
        rul = segment["true_rul_h"].to_numpy()
        assert (rul[1:] <= rul[:-1] + 1e-9).all()
    failure = cnc[cnc["state"] == "DOWN"].iloc[0]
    assert (failure["failure_mode"], failure["driver"], failure["true_rul_h"]) == (
        "bearing_wear",
        "spindle.vib_rms",
        0.0,
    )
    hours_to_failure = (failure["time"] - cnc["time"].iloc[0]).total_seconds() / 3600
    assert hours_to_failure == pytest.approx(6.75, abs=0.1)
    assert cnc["true_rul_h"].iloc[0] == pytest.approx(6.75, abs=0.05)
    assert cnc["state"].iloc[-1] == "RUNNING"


def test_export_validates_hours(catalog: Catalog, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        export_run(catalog, hours=0.0, out_dir=tmp_path)
    with pytest.raises(ValueError):
        export_run(catalog, hours=200.0, out_dir=tmp_path)
