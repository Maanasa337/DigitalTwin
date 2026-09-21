from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.models import AuditLog
from app.modules.twin.service import machine_health, mean_health
from tests.conftest import FakeCommands, FakeDitto, auth

API = "/api/v1"
PIN = "246810"


@pytest.mark.parametrize(
    ("components", "expected"),
    [
        ([], None),
        ([(None, 1.0), (None, 0.5)], None),
        ([(90.0, 1.0), (None, 1.0)], 90.0),
        ([(90.0, 1.0), (80.0, 0.5)], 40.0),
        ([(0.0, 1.0), (95.0, 1.0)], 0.0),
    ],
)
def test_machine_health_is_weighted_min_of_reporting_components(
    components: list[tuple[float | None, float]], expected: float | None
) -> None:
    assert machine_health(components) == expected


def test_mean_health_ignores_unknown() -> None:
    assert mean_health([None, None]) is None
    assert mean_health([80.0, None, 60.0]) == 70.0


def test_tree_rolls_health_up_from_components(
    client: TestClient, ditto: FakeDitto, seeded_asset: dict[str, Any]
) -> None:
    ditto.set_live(
        "cnc-01",
        "components",
        {
            "spindle": {"health": 72.0, "rul": {"point": 38, "low": 29, "high": 47, "unit": "cycles"}},
            "motor": {"health": 95.0},
        },
    )

    tree = client.get(f"{API}/twin/tree", headers=auth("technician")).json()

    [plant] = tree["plants"]
    [line] = plant["lines"]
    [asset] = line["assets"]
    assert asset["code"] == "cnc-01"
    assert asset["health"] == 72.0  # min(72 x 1.0, 95 x 0.8 = 76)
    assert line["health"] == 72.0 and plant["health"] == 72.0
    spindle = next(c for c in asset["components"] if c["code"] == "spindle")
    assert spindle["rul"] == {"point": 38, "low": 29, "high": 47, "unit": "cycles"}


def test_tree_survives_twin_store_outage(client: TestClient, ditto: FakeDitto, seeded_asset: dict[str, Any]) -> None:
    ditto.available = False
    resp = client.get(f"{API}/twin/tree", headers=auth("technician"))
    assert resp.status_code == 200
    asset = resp.json()["plants"][0]["lines"][0]["assets"][0]
    assert asset["health"] is None
    assert {c["health"] for c in asset["components"]} == {None}


def test_tree_excludes_retired_assets(client: TestClient, seeded_asset: dict[str, Any]) -> None:
    client.delete(f"{API}/assets/{seeded_asset['id']}", headers=auth("engineer"))
    tree = client.get(f"{API}/twin/tree", headers=auth("technician")).json()
    assert tree["plants"][0]["lines"][0]["assets"] == []


def test_get_twin_merges_registry_and_store(client: TestClient, ditto: FakeDitto, seeded_asset: dict[str, Any]) -> None:
    ditto.set_live("cnc-01", "telemetry", {"power_kw": {"v": 12.5, "u": "kW", "t": "2026-09-17T10:00:00Z"}})
    twin = client.get(f"{API}/twin/cnc-01", headers=auth("manager")).json()
    assert twin["thing_id"] == "twinvoice:cnc-01"
    assert twin["policy_id"] == "twinvoice:active"
    assert twin["fidelity_level"] == 3
    assert twin["features"]["telemetry"]["properties"]["power_kw"]["v"] == 12.5
    assert client.get(f"{API}/twin/nope-99", headers=auth("manager")).status_code == 404


def _command(client: TestClient, role: str = "engineer", **body: Any) -> Any:
    payload = {"command": "set_load", "params": {"load_pct": 80}, "pin": PIN, **body}
    return client.post(f"{API}/twin/cnc-01/commands", json=payload, headers=auth(role))


def _command_audits(session: Session) -> list[AuditLog]:
    return list(session.scalars(select(AuditLog).where(AuditLog.action == "execute")))


def test_command_accepted_is_published_and_audited_without_pin(
    client: TestClient, session: Session, commands: FakeCommands, seeded_asset: dict[str, Any]
) -> None:
    resp = _command(client)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"command_id": "cmd-1", "command": "set_load", "status": "accepted", "error": None}
    assert commands.sent == [
        {"command_id": "cmd-1", "asset": "cnc-01", "command": "set_load", "params": {"load_pct": 80.0}}
    ]
    [audit] = _command_audits(session)
    assert audit.after is not None
    assert audit.after["status"] == "accepted" and audit.after["tier"] == "T3"
    assert PIN not in str(audit.after)


def test_command_rejected_by_machine_is_reported(
    client: TestClient, commands: FakeCommands, seeded_asset: dict[str, Any]
) -> None:
    commands.reply = lambda cmd: {"command_id": cmd["command_id"], "status": "rejected", "error": "asset is DOWN"}
    resp = _command(client, command="maintenance_reset", params={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected" and resp.json()["error"] == "asset is DOWN"


def test_command_timeout_is_504_and_still_audited(
    client: TestClient, session: Session, commands: FakeCommands, seeded_asset: dict[str, Any]
) -> None:
    commands.reply = lambda cmd: None
    resp = _command(client)
    assert resp.status_code == 504
    [audit] = _command_audits(session)
    assert audit.after is not None and audit.after["status"] == "timeout"


def test_command_requires_t3_switch_role_and_pin(
    client: TestClient, session: Session, commands: FakeCommands, settings: Settings, seeded_asset: dict[str, Any]
) -> None:
    assert _command(client, role="technician").status_code == 403
    assert _command(client, pin=None).status_code == 423
    assert _command(client, pin="000000").status_code == 423
    assert _command(client, params={"load_pct": 150}).status_code == 422
    assert _command(client, command="self_destruct").status_code == 422

    settings.allow_t3 = False
    disabled = _command(client)
    assert disabled.status_code == 403
    assert "TV_ALLOW_T3" in disabled.json()["detail"]

    assert commands.sent == [] and _command_audits(session) == []
