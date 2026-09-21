from pathlib import Path

import pytest

from sim.replay import read_ai4i, read_cmapss, read_metropt3, replay, snake_case
from sim.sensors import MetricDef

from .conftest import FIXTURES


def test_cmapss_parser() -> None:
    rows = list(read_cmapss(FIXTURES / "train_FD001_sample.txt"))
    assert [r.asset_code for r in rows] == ["engine-001"] * 3 + ["engine-002"] * 2
    first = rows[0].values
    assert list(first) == [f"engine.op{i}" for i in (1, 2, 3)] + [
        f"engine.s{i:02d}" for i in range(1, 22)
    ]
    assert first["engine.op1"] == -0.0007
    assert first["engine.s02"] == 641.82
    assert first["engine.s21"] == 23.419


def test_cmapss_unit_filter() -> None:
    rows = list(read_cmapss(FIXTURES / "train_FD001_sample.txt", {2}))
    assert {r.asset_code for r in rows} == {"engine-002"}


def test_cmapss_rejects_wrong_width(tmp_path: Path) -> None:
    bad = tmp_path / "bad.txt"
    bad.write_text("1 1 0.1 0.2\n")
    with pytest.raises(ValueError):
        list(read_cmapss(bad))


def test_ai4i_parser() -> None:
    rows = list(read_ai4i(FIXTURES / "ai4i2020_sample.csv"))
    assert len(rows) == 3
    assert rows[0].asset_code == "ai4i-mill"
    assert rows[0].values == {
        "mill.air_temp_k": 298.1,
        "mill.process_temp_k": 308.6,
        "mill.rpm": 1551.0,
        "mill.torque_nm": 42.8,
        "mill.tool_wear_min": 0.0,
    }


def test_metropt3_parser() -> None:
    rows = list(read_metropt3(FIXTURES / "metropt3_sample.csv"))
    assert len(rows) == 3
    assert rows[0].asset_code == "metro-apu"
    assert list(rows[0].values)[:4] == ["apu.tp2", "apu.tp3", "apu.h1", "apu.dv_pressure"]
    assert rows[0].values["apu.oil_temperature"] == pytest.approx(53.6)
    assert rows[0].values["apu.caudal_impulses"] == 1.0
    assert "apu.timestamp" not in rows[0].values


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("DV_pressure", "dv_pressure"),
        ("Oil_temperature", "oil_temperature"),
        ("TP2", "tp2"),
        ("MotorCurrent", "motor_current"),
    ],
)
def test_snake_case(raw: str, expected: str) -> None:
    assert snake_case(raw) == expected


class FakeNode:
    def __init__(self) -> None:
        self.defs: dict[str, list[MetricDef]] = {}
        self.published: list[tuple[str, dict]] = []

    @property
    def devices(self) -> set[str]:
        return set(self.defs)

    def add_device(self, device: str, defs: list[MetricDef]) -> None:
        self.defs[device] = defs

    def publish_device(self, device: str, values: dict, jitter: dict) -> None:
        self.published.append((device, values))


def test_replay_publishes_rows_through_edge_node() -> None:
    node = FakeNode()
    sleeps: list[float] = []
    sent = replay("ai4i", FIXTURES / "ai4i2020_sample.csv", 1000.0, node, sleep=sleeps.append)  # type: ignore[arg-type]
    assert sent == 3 == len(node.published) == len(sleeps)
    assert [d.unit for d in node.defs["ai4i-mill"]] == ["K", "K", "rpm", "Nm", "min"]
