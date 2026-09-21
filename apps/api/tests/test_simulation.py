from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import AuditLog
from app.modules.simulation.models import Scenario, ScenarioRun
from tests.conftest import FakeSimulator, auth

API = "/api/v1"


def test_status_is_proxied_for_engineers_only(client: TestClient, simulator: FakeSimulator) -> None:
    simulator.routes[("GET", "/status")] = lambda _: httpx.Response(200, json={"time_scale": 60.0, "assets": []})

    assert client.get(f"{API}/simulation/status", headers=auth("engineer")).json() == {"time_scale": 60.0, "assets": []}
    assert client.get(f"{API}/simulation/status", headers=auth("technician")).status_code == 403


def test_simulator_down_is_503_problem(client: TestClient, simulator: FakeSimulator) -> None:
    simulator.up = False
    resp = client.get(f"{API}/simulation/status", headers=auth("engineer"))
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Simulator unreachable"


def test_fault_injection_checks_asset_then_audits(
    client: TestClient, session: Session, simulator: FakeSimulator, seeded_asset: dict[str, Any]
) -> None:
    simulator.routes[("POST", "/faults")] = lambda body: httpx.Response(
        200, json={"accepted": True, "asset": body["asset"], "failure_mode": body["failure_mode"]}
    )

    unknown = client.post(
        f"{API}/simulation/faults", json={"asset": "ghost-1", "failure_mode": "x"}, headers=auth("engineer")
    )
    assert unknown.status_code == 404
    assert simulator.calls == []

    body = {"asset": "cnc-01", "failure_mode": "bearing_wear", "mode": "gradual", "severity": 0.8}
    resp = client.post(f"{API}/simulation/faults", json=body, headers=auth("engineer"))
    assert resp.status_code == 200 and resp.json()["accepted"] is True
    [audit] = session.scalars(select(AuditLog).where(AuditLog.action == "inject_fault"))
    assert audit.after is not None and audit.after["failure_mode"] == "bearing_wear"


def test_simulator_validation_errors_pass_through_as_422(
    client: TestClient, simulator: FakeSimulator, seeded_asset: dict[str, Any]
) -> None:
    simulator.routes[("POST", "/faults")] = lambda _: httpx.Response(422, json={"detail": "unknown failure mode 'x'"})
    resp = client.post(
        f"{API}/simulation/faults", json={"asset": "cnc-01", "failure_mode": "x"}, headers=auth("engineer")
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "unknown failure mode 'x'"


def test_starting_a_scenario_closes_the_previous_run(
    client: TestClient, session: Session, simulator: FakeSimulator
) -> None:
    session.add_all(
        [Scenario(code="demo_day", name="Demo", yaml="code: demo_day"), Scenario(code="s2", name="S2", yaml="x")]
    )
    session.commit()  # a savepoint rollback from the 404 below must not undo the fixture rows
    simulator.routes[("POST", "/scenario")] = lambda body: httpx.Response(
        200,
        json={
            "scenario_code": body["scenario_code"],
            "started_at": "2026-09-17T10:00:00Z",
            "seed": 7,
            "time_scale": 60,
        },
    )

    assert (
        client.post(
            f"{API}/simulation/scenario", json={"scenario_code": "missing"}, headers=auth("engineer")
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{API}/simulation/scenario", json={"scenario_code": "demo_day"}, headers=auth("engineer")
        ).status_code
        == 200
    )
    assert (
        client.post(f"{API}/simulation/scenario", json={"scenario_code": "s2"}, headers=auth("admin")).status_code
        == 200
    )

    runs = {r.scenario_code: r for r in session.scalars(select(ScenarioRun))}
    assert runs["demo_day"].ended_at is not None
    assert runs["s2"].ended_at is None and runs["s2"].seed == 7 and runs["s2"].time_scale == 60
    assert [s["code"] for s in client.get(f"{API}/simulation/scenarios", headers=auth("engineer")).json()] == [
        "demo_day",
        "s2",
    ]


def test_time_scale_bounds_reset_and_export(
    client: TestClient, session: Session, simulator: FakeSimulator, seeded_asset: dict[str, Any]
) -> None:
    simulator.routes[("POST", "/time-scale")] = lambda body: httpx.Response(200, json={"time_scale": body["factor"]})
    simulator.routes[("POST", "/reset/cnc-01")] = lambda _: httpx.Response(
        200, json={"asset": "cnc-01", "reset_components": ["spindle"]}
    )
    simulator.routes[("POST", "/export")] = lambda _: httpx.Response(
        200, json={"path": "/data/synthetic/baseline_seed1.parquet", "rows": 8640, "columns": ["time"]}
    )

    assert (
        client.post(f"{API}/simulation/time-scale", json={"factor": 5000}, headers=auth("engineer")).status_code == 422
    )
    assert client.post(f"{API}/simulation/time-scale", json={"factor": 100}, headers=auth("engineer")).json() == {
        "time_scale": 100
    }

    reset = client.post(f"{API}/simulation/reset/cnc-01", json={"component_code": "spindle"}, headers=auth("engineer"))
    assert reset.status_code == 200
    assert simulator.calls[-1] == ("POST", "/reset/cnc-01", {"component_code": "spindle"})
    assert client.post(f"{API}/simulation/reset/cnc-01", headers=auth("engineer")).status_code == 200, (
        "body is optional"
    )

    export = client.post(f"{API}/simulation/export", json={"hours": 24, "seed": 1}, headers=auth("engineer"))
    assert export.status_code == 200
    [run] = session.scalars(select(ScenarioRun).where(ScenarioRun.export_uri.is_not(None)))
    assert run.export_uri == "/data/synthetic/baseline_seed1.parquet" and run.ended_at is not None
    actions = set(session.scalars(select(AuditLog.action)))
    assert {"time_scale", "reset", "export"} <= actions
