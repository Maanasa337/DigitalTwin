from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sim.api import create_app
from sim.catalog import Catalog
from sim.live import LiveRuntime

STATUS_KEYS = {
    "sim_time",
    "sim_elapsed_s",
    "time_scale",
    "running",
    "seed",
    "scenario",
    "assets",
    "log",
}
ASSET_KEYS = {
    "code", "asset_type", "line_code", "state", "load_pct", "speed_pct", "damage", "active_modes",
    "sensor_faults", "true_rul_h", "driver", "failure_mode",
}  # fmt: skip


@pytest.fixture
def client(catalog: Catalog, tmp_path: Path) -> TestClient:
    runtime = LiveRuntime(catalog, seed=42, time_scale=60.0)
    runtime.tick()
    return TestClient(create_app(runtime, tmp_path))


def test_health_and_catalog(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    catalog = client.get("/catalog").json()
    assert len(catalog["assets"]) == 10
    assert catalog["assets"][0]["modbus"]["unit_id"] == 1


def test_status_shape(client: TestClient) -> None:
    body = client.get("/status").json()
    assert set(body) == STATUS_KEYS
    assert body["time_scale"] == 60.0
    assert body["running"] is False
    assert body["seed"] == 42
    assert body["scenario"] is None
    assert body["sim_time"].endswith("Z")
    assert body["sim_elapsed_s"] == 60.0
    assert len(body["assets"]) == 10
    for asset in body["assets"]:
        assert set(asset) == ASSET_KEYS
        assert isinstance(asset["damage"], dict) and asset["damage"]
        assert asset["true_rul_h"] is None or asset["true_rul_h"] >= 0
        assert isinstance(asset["failure_mode"], str)


def test_faults(client: TestClient) -> None:
    ok = client.post("/faults", json={"asset": "cnc-01", "failure_mode": "bearing_wear"})
    assert ok.status_code == 200
    assert ok.json() == {"accepted": True, "asset": "cnc-01", "failure_mode": "bearing_wear"}
    sensor = {
        "asset": "cnc-01",
        "failure_mode": "sensor_offset",
        "metric": "spindle.temp",
        "duration_s": 60,
    }
    assert client.post("/faults", json=sensor).status_code == 200
    status = client.get("/status").json()
    cnc = next(a for a in status["assets"] if a["code"] == "cnc-01")
    assert cnc["active_modes"][0]["failure_mode"] == "bearing_wear"
    assert cnc["active_modes"][0]["mode"] == "gradual"
    assert cnc["active_modes"][0]["severity"] == 0.5
    assert cnc["sensor_faults"][0]["kind"] == "sensor_offset"
    assert any(e["level"] == "warning" and e["asset_code"] == "cnc-01" for e in status["log"])


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"asset": "cnc-99", "failure_mode": "bearing_wear"}, 404),
        ({"asset": "cnc-01", "failure_mode": "belt_slip"}, 422),
        ({"asset": "cnc-01", "failure_mode": "sensor_stuck"}, 422),
        ({"asset": "cnc-01", "failure_mode": "sensor_stuck", "metric": "nope"}, 422),
        ({"asset": "cnc-01", "failure_mode": "bearing_wear", "severity": 2}, 422),
        ({"asset": "cnc-01", "failure_mode": "bearing_wear", "mode": "slow"}, 422),
    ],
)
def test_fault_errors(client: TestClient, body: dict, code: int) -> None:
    response = client.post("/faults", json=body)
    assert response.status_code == code
    assert "detail" in response.json()


def test_time_scale(client: TestClient) -> None:
    assert client.post("/time-scale", json={"factor": 500}).json() == {"time_scale": 500.0}
    assert client.get("/status").json()["time_scale"] == 500.0
    assert client.post("/time-scale", json={"factor": 0.5}).status_code == 422
    assert client.post("/time-scale", json={"factor": 1001}).status_code == 422


def test_reset(client: TestClient) -> None:
    everything = client.post("/reset/conveyor-01")
    assert everything.json() == {
        "asset": "conveyor-01",
        "reset_components": ["bearing", "drive", "belt", "motor"],
    }
    one = client.post("/reset/conveyor-01", json={"component_code": "belt"})
    assert one.json() == {"asset": "conveyor-01", "reset_components": ["belt"]}
    assert client.post("/reset/conveyor-99").status_code == 404
    assert client.post("/reset/conveyor-01", json={"component_code": "tool"}).status_code == 422
    conveyor = next(a for a in client.get("/status").json()["assets"] if a["code"] == "conveyor-01")
    assert conveyor["state"] == "MAINTENANCE"


def test_scenario(client: TestClient) -> None:
    response = client.post("/scenario", json={"scenario_code": "user_study_a"})
    assert response.status_code == 200
    body = response.json()
    assert (body["scenario_code"], body["seed"], body["time_scale"]) == ("user_study_a", 101, 60.0)
    assert body["started_at"].endswith("Z")
    status = client.get("/status").json()
    assert status["scenario"]["code"] == "user_study_a"
    assert status["sim_time"] == "2026-01-05T00:30:00.000Z"
    assert client.post("/scenario", json={"scenario_code": "nope"}).status_code == 404


def test_export(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/export", json={"hours": 0.5, "sample_period_s": 300})
    assert response.status_code == 200
    body = response.json()
    assert body["rows"] == 60
    assert Path(body["path"]).exists()
    assert body["columns"][:2] == ["time", "asset_code"]
    assert client.post("/export", json={"hours": 0}).status_code == 422
    assert client.post("/export", json={"hours": 200}).status_code == 422
    assert client.post("/export", json={"hours": 1, "scenario_code": "nope"}).status_code == 404
