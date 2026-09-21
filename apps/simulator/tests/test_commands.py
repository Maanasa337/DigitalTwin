import json
from datetime import datetime

import pytest

from sim.catalog import Catalog
from sim.commands import handle_command
from sim.live import LiveRuntime
from sim.machines import State


@pytest.fixture
def runtime(catalog: Catalog) -> LiveRuntime:
    return LiveRuntime(catalog, seed=9, time_scale=1.0)


def send(runtime: LiveRuntime, asset: str, command: str, params: object, **extra: object) -> dict:
    body = {"command_id": "cmd-1", "params": params, "issued_by": "tester", "tier": "T3", **extra}
    return handle_command(runtime, asset, command, json.dumps(body).encode())


def assert_ack_shape(ack: dict, command: str, status: str) -> None:
    assert set(ack) == {"command_id", "command", "status", "error", "t"}
    assert ack["command"] == command
    assert ack["status"] == status
    assert (ack["error"] is None) == (status == "accepted")
    assert ack["t"].endswith("Z")
    datetime.fromisoformat(ack["t"])


def test_set_load_accepted(runtime: LiveRuntime) -> None:
    ack = send(runtime, "cnc-01", "set_load", {"load_pct": 75})
    assert_ack_shape(ack, "set_load", "accepted")
    assert ack["command_id"] == "cmd-1"
    assert runtime.engine.machines["cnc-01"].load_setpoint_pct == 75.0


def test_set_speed_accepted_and_range_checked(runtime: LiveRuntime) -> None:
    assert_ack_shape(
        send(runtime, "press-01", "set_speed", {"speed_pct": 110}), "set_speed", "accepted"
    )
    assert runtime.engine.machines["press-01"].speed_setpoint_pct == 110.0
    ack = send(runtime, "press-01", "set_speed", {"speed_pct": 40})
    assert_ack_shape(ack, "set_speed", "rejected")
    assert "speed_pct" in ack["error"]


def test_maintenance_reset_all_and_one_component(runtime: LiveRuntime) -> None:
    ack = send(runtime, "compressor-01", "maintenance_reset", {"component_code": None})
    assert_ack_shape(ack, "maintenance_reset", "accepted")
    machine = runtime.engine.machines["compressor-01"]
    assert machine.state is State.MAINTENANCE
    assert all(d == 0.0 for d in machine.ground_truth().damage.values())
    ack = send(runtime, "compressor-02", "maintenance_reset", {"component_code": "bearing"})
    assert_ack_shape(ack, "maintenance_reset", "accepted")
    ack = send(runtime, "compressor-02", "maintenance_reset", {"component_code": "spindle"})
    assert_ack_shape(ack, "maintenance_reset", "rejected")


@pytest.mark.parametrize(
    ("asset", "command", "params", "error"),
    [
        ("cnc-99", "set_load", {"load_pct": 50}, "unknown asset cnc-99"),
        ("cnc-01", "self_destruct", {}, "unknown command self_destruct"),
        ("cnc-01", "set_load", {"load_pct": 111}, "load_pct must be within 0..110"),
        ("cnc-01", "set_load", {"load_pct": "high"}, "params.load_pct must be a number"),
        ("cnc-01", "set_load", {}, "params.load_pct must be a number"),
        ("cnc-01", "set_load", [1, 2], "params must be an object"),
    ],
)
def test_rejections(
    runtime: LiveRuntime, asset: str, command: str, params: object, error: str
) -> None:
    ack = send(runtime, asset, command, params)
    assert_ack_shape(ack, command, "rejected")
    assert ack["error"] == error


def test_malformed_payloads_are_rejected(runtime: LiveRuntime) -> None:
    ack = handle_command(runtime, "cnc-01", "set_load", b"not json")
    assert_ack_shape(ack, "set_load", "rejected")
    assert ack["command_id"] is None
    ack = handle_command(runtime, "cnc-01", "set_load", b'{"params": {"load_pct": 50}}')
    assert ack["error"] == "command_id is required"


def test_commands_are_logged(runtime: LiveRuntime) -> None:
    send(runtime, "cnc-01", "set_load", {"load_pct": 60})
    send(runtime, "cnc-01", "set_load", {"load_pct": 600})
    messages = [entry["message"] for entry in runtime.status()["log"]]
    assert "Command set_load from tester accepted" in messages
    assert any(m.startswith("Command set_load from tester rejected") for m in messages)
