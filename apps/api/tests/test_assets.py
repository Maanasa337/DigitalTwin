import io
import uuid
import zipfile
from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.models import AuditLog
from app.modules.assets import aas
from app.modules.assets.models import AasSubmodel, Asset, Component, Sensor
from app.modules.twin import policies
from tests.conftest import FakeDitto, auth

API = "/api/v1"


def asset_body(line_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "line_id": line_id,
        "code": "press-09",
        "name": "Hydraulic Press 09",
        "asset_type": "hydraulic_press",
        "manufacturer": "Hydro",
        "model": "HP-200",
        "serial_no": "HP200-9",
        "install_date": "2024-02-01",
        "rated_power_kw": 22.5,
        **overrides,
    }


def audit_rows(session: Session, entity: str, entity_id: str) -> list[AuditLog]:
    return list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.entity == entity, AuditLog.entity_id == uuid.UUID(entity_id))
            .order_by(AuditLog.id)
        )
    )


def test_create_asset_persists_row_twin_submodels_and_audit(
    client: TestClient, session: Session, ditto: FakeDitto, plant_line: dict[str, Any]
) -> None:
    resp = client.post(f"{API}/assets", json=asset_body(plant_line["line"]["id"]), headers=auth("engineer"))

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ditto_thing_id"] == "twinvoice:press-09"
    assert body["aas_id"] == "https://twinvoice.dev/aas/press-09"
    assert body["rated_power_kw"] == 22.5
    thing = ditto.things["twinvoice:press-09"]
    assert thing["policyId"] == policies.ACTIVE_POLICY_ID
    assert thing["attributes"]["line_code"] == "line-t"
    assert thing["attributes"]["plant_code"] == "plant-t"
    assert thing["features"]["state"]["properties"]["status"] == "RUNNING"
    stored = session.scalars(select(AasSubmodel.id_short).where(AasSubmodel.asset_id == uuid.UUID(body["id"])))
    assert sorted(stored) == ["Nameplate", "TechnicalData"]
    [row] = audit_rows(session, "assets", body["id"])
    assert row.action == "create"
    assert row.actor_kind == "user"
    assert row.after is not None and row.after["code"] == "press-09"


def test_write_endpoints_require_engineer_or_admin(client: TestClient, plant_line: dict[str, Any]) -> None:
    body = asset_body(plant_line["line"]["id"])
    forbidden = client.post(f"{API}/assets", json=body, headers=auth("technician"))
    assert forbidden.status_code == 403
    assert forbidden.headers["content-type"] == "application/problem+json"
    assert forbidden.json()["title"] == "Forbidden"

    unauthenticated = client.post(f"{API}/assets", json=body)
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["www-authenticate"] == "Bearer"

    assert client.post(f"{API}/assets", json=body, headers=auth("admin")).status_code == 201
    assert client.get(f"{API}/assets", headers=auth("technician")).status_code == 200


def test_create_asset_validation_and_conflicts(client: TestClient, plant_line: dict[str, Any]) -> None:
    line_id = plant_line["line"]["id"]
    bad_code = client.post(f"{API}/assets", json=asset_body(line_id, code="Press 9"), headers=auth("engineer"))
    assert bad_code.status_code == 422
    assert bad_code.json()["errors"][0]["loc"] == ["body", "code"]

    unknown_line = client.post(f"{API}/assets", json=asset_body(str(uuid.uuid4())), headers=auth("engineer"))
    assert unknown_line.status_code == 422

    assert client.post(f"{API}/assets", json=asset_body(line_id), headers=auth("engineer")).status_code == 201
    duplicate = client.post(f"{API}/assets", json=asset_body(line_id, name="Other"), headers=auth("engineer"))
    assert duplicate.status_code == 409


def test_twin_store_outage_rolls_back_asset_creation(
    client: TestClient, session: Session, ditto: FakeDitto, plant_line: dict[str, Any]
) -> None:
    ditto.available = False
    resp = client.post(f"{API}/assets", json=asset_body(plant_line["line"]["id"]), headers=auth("engineer"))

    assert resp.status_code == 503
    assert session.scalar(select(func.count()).select_from(Asset).where(Asset.code == "press-09")) == 0
    assert session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity == "assets")) == 0


def test_list_assets_filters_paginates_and_rejects_unknown_sort(client: TestClient, plant_line: dict[str, Any]) -> None:
    line_id = plant_line["line"]["id"]
    for i, kind in enumerate(["conveyor", "conveyor", "compressor"]):
        body = asset_body(line_id, code=f"asset-{i}", name=f"Asset {i}", asset_type=kind)
        assert client.post(f"{API}/assets", json=body, headers=auth("engineer")).status_code == 201

    page = client.get(
        f"{API}/assets", params={"asset_type": "conveyor", "size": 1, "sort": "-code"}, headers=auth("manager")
    )
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert [a["code"] for a in page.json()["items"]] == ["asset-1"]

    search = client.get(f"{API}/assets", params={"q": "SET-2"}, headers=auth("manager")).json()
    assert [a["code"] for a in search["items"]] == ["asset-2"]

    assert client.get(f"{API}/assets", params={"sort": "serial_no"}, headers=auth("manager")).status_code == 422


def test_update_merges_twin_attributes_and_audits_before_after(
    client: TestClient, session: Session, ditto: FakeDitto, seeded_asset: dict[str, Any]
) -> None:
    ditto.set_live("cnc-01", "telemetry", {"power_kw": {"v": 11.2, "u": "kW", "t": "2026-09-17T10:00:00Z"}})
    resp = client.patch(
        f"{API}/assets/{seeded_asset['id']}",
        json={"name": "CNC Mill 01A", "status": "MAINTENANCE"},
        headers=auth("engineer"),
    )

    assert resp.status_code == 200, resp.text
    thing = ditto.things["twinvoice:cnc-01"]
    assert thing["attributes"]["name"] == "CNC Mill 01A"
    assert thing["features"]["state"]["properties"]["status"] == "MAINTENANCE"
    assert thing["features"]["telemetry"]["properties"]["power_kw"]["v"] == 11.2, "update must not wipe live data"
    update = audit_rows(session, "assets", seeded_asset["id"])[-1]
    assert update.action == "update"
    assert update.before is not None and update.after is not None
    assert (update.before["name"], update.after["name"]) == ("CNC Mill 01", "CNC Mill 01A")


def test_retire_makes_twin_read_only_hides_asset_and_blocks_code_reuse(
    client: TestClient, ditto: FakeDitto, seeded_asset: dict[str, Any]
) -> None:
    resp = client.delete(f"{API}/assets/{seeded_asset['id']}", headers=auth("engineer"))

    assert resp.status_code == 204
    assert ditto.things["twinvoice:cnc-01"]["policyId"] == policies.RETIRED_POLICY_ID
    assert client.get(f"{API}/assets/{seeded_asset['id']}", headers=auth("engineer")).status_code == 404
    reuse = client.post(
        f"{API}/assets", json=asset_body(seeded_asset["line_id"], code="cnc-01"), headers=auth("engineer")
    )
    assert reuse.status_code == 409
    assert "retired" in reuse.json()["detail"]


def test_clone_copies_components_and_sensors_but_not_serial(
    client: TestClient, session: Session, ditto: FakeDitto, seeded_asset: dict[str, Any]
) -> None:
    resp = client.post(
        f"{API}/assets/{seeded_asset['id']}/clone",
        json={"code": "cnc-02", "name": "CNC Mill 02"},
        headers=auth("engineer"),
    )

    assert resp.status_code == 201, resp.text
    clone = resp.json()
    assert (clone["model"], clone["serial_no"], clone["fidelity_level"]) == ("VMC-850", None, 3)
    sensors = client.get(f"{API}/assets/{clone['id']}/sensors", headers=auth("engineer")).json()
    components = {
        c["id"]: c["code"]
        for c in client.get(f"{API}/assets/{clone['id']}/components", headers=auth("engineer")).json()
    }
    assert sorted(components.values()) == ["motor", "spindle"]
    by_metric = {s["metric_name"]: s for s in sensors}
    assert components[by_metric["spindle.vib_rms"]["component_id"]] == "spindle"
    assert by_metric["spindle.vib_rms"]["alarm_high"] == 7.1
    assert by_metric["power_kw"]["component_id"] is None
    assert set(ditto.things["twinvoice:cnc-02"]["features"]["components"]["properties"]) == {"spindle", "motor"}


def test_add_component_extends_twin(client: TestClient, ditto: FakeDitto, seeded_asset: dict[str, Any]) -> None:
    resp = client.post(
        f"{API}/components",
        json={"asset_id": seeded_asset["id"], "code": "coolant", "name": "Coolant pump", "component_type": "pump"},
        headers=auth("engineer"),
    )
    assert resp.status_code == 201, resp.text
    assert "coolant" in ditto.things["twinvoice:cnc-01"]["features"]["components"]["properties"]
    duplicate = client.post(
        f"{API}/components",
        json={"asset_id": seeded_asset["id"], "code": "coolant", "name": "Again", "component_type": "pump"},
        headers=auth("engineer"),
    )
    assert duplicate.status_code == 409


def test_aas_environment_has_five_submodels_with_live_values(
    client: TestClient, ditto: FakeDitto, seeded_asset: dict[str, Any]
) -> None:
    ditto.set_live("cnc-01", "telemetry", {"spindle.vib_rms": {"v": 2.31, "u": "mm/s", "t": "2026-09-17T10:00:00Z"}})
    ditto.set_live(
        "cnc-01", "prediction", {"health_index": 71.2, "rul": {"point": 38, "low": 29, "high": 47, "unit": "cycles"}}
    )

    env = client.get(f"{API}/assets/{seeded_asset['id']}/aas", headers=auth("technician")).json()

    [shell] = env["assetAdministrationShells"]
    assert shell["assetInformation"]["globalAssetId"] == "https://twinvoice.dev/assets/cnc-01"
    submodels = {sm["idShort"]: sm for sm in env["submodels"]}
    assert set(submodels) == {
        "Nameplate",
        "TechnicalData",
        "OperationalData",
        "MaintenanceHistory",
        "PredictiveMaintenance",
    }
    assert len(shell["submodels"]) == 5

    def element(elements: list[dict[str, Any]], id_short: str) -> dict[str, Any]:
        return next(e for e in elements if e["idShort"] == id_short)

    spindle = element(element(submodels["OperationalData"]["submodelElements"], "Components")["value"], "spindle")
    vib = element(element(spindle["value"], "Sensors")["value"], "spindle_vib_rms")
    assert element(vib["value"], "CurrentValue")["value"] == "2.31"
    assert element(submodels["PredictiveMaintenance"]["submodelElements"], "HealthIndex")["value"] == "71.2"
    maker = element(submodels["Nameplate"]["submodelElements"], "ManufacturerName")
    assert maker["value"] == [{"language": "en", "text": "Acme"}]


def test_aas_still_renders_when_twin_store_is_down(
    client: TestClient, ditto: FakeDitto, seeded_asset: dict[str, Any]
) -> None:
    ditto.available = False
    resp = client.get(f"{API}/assets/{seeded_asset['id']}/aas", headers=auth("technician"))
    assert resp.status_code == 200
    assert len(resp.json()["submodels"]) == 5


def test_aasx_export_is_a_valid_package_that_imports_back(
    client: TestClient, session: Session, seeded_asset: dict[str, Any]
) -> None:
    exported = client.get(f"{API}/assets/{seeded_asset['id']}/aas.aasx", headers=auth("technician"))
    assert exported.status_code == 200
    assert exported.headers["content-disposition"] == 'attachment; filename="cnc-01.aasx"'
    assert "[Content_Types].xml" in zipfile.ZipFile(io.BytesIO(exported.content)).namelist()

    imported = aas.read_aasx(exported.content)
    assert (imported.code, imported.name, imported.manufacturer, imported.product_model) == (
        "cnc-01", "CNC Mill 01", "Acme", "VMC-850"
    )  # fmt: skip
    assert imported.rated_power_kw == 15.0
    assert [c.code for c in imported.components] == ["motor", "spindle"]
    assert {s.metric_name: s.component_code for s in imported.sensors} == {
        "spindle.vib_rms": "spindle", "motor.current": "motor", "power_kw": None,
    }  # fmt: skip

    # Import the same package as a new asset: rename the global asset id so the code is free.
    retargeted = _rewrite_code(exported.content, "cnc-01", "cnc-77")
    resp = client.post(
        f"{API}/assets/import-aasx",
        files={"file": ("cnc-77.aasx", retargeted, "application/octet-stream")},
        data={"line_id": seeded_asset["line_id"], "asset_type": "cnc_mill"},
        headers=auth("engineer"),
    )
    assert resp.status_code == 201, resp.text
    new_id = uuid.UUID(resp.json()["id"])
    assert session.scalar(select(func.count()).select_from(Sensor).where(Sensor.asset_id == new_id)) == 3
    assert session.scalar(select(func.count()).select_from(Component).where(Component.asset_id == new_id)) == 2


def _rewrite_code(package: bytes, old: str, new: str) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(package))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.endswith(".json"):
                data = data.replace(f"/{old}".encode(), f"/{new}".encode())
            target.writestr(item, data)
    return out.getvalue()


def test_import_rejects_garbage(client: TestClient, seeded_asset: dict[str, Any]) -> None:
    resp = client.post(
        f"{API}/assets/import-aasx",
        files={"file": ("x.aasx", b"not a zip", "application/octet-stream")},
        data={"line_id": seeded_asset["line_id"], "asset_type": "cnc_mill"},
        headers=auth("engineer"),
    )
    assert resp.status_code == 422


def test_dtdl_and_ngsi_ld_adapters(client: TestClient, ditto: FakeDitto, seeded_asset: dict[str, Any]) -> None:
    ditto.set_live("cnc-01", "telemetry", {"spindle.vib_rms": {"v": 2.31, "u": "mm/s", "t": "2026-09-17T10:00:00Z"}})

    dtdl = client.get(f"{API}/assets/{seeded_asset['id']}/dtdl", headers=auth("technician")).json()
    assert dtdl["@id"] == "dtmi:twinvoice:asset:cnc_01;1"
    spindle = next(c for c in dtdl["contents"] if c["@type"] == "Component" and c["name"] == "spindle")
    assert [t["name"] for t in spindle["schema"]["contents"] if t["@type"] == "Telemetry"] == ["vib_rms"]
    assert any(c["@type"] == "Telemetry" and c["name"] == "power_kw" for c in dtdl["contents"])

    resp = client.get(f"{API}/assets/{seeded_asset['id']}/ngsi-ld", headers=auth("technician"))
    assert resp.headers["content-type"] == "application/ld+json"
    entity = resp.json()
    assert entity["id"] == "urn:ngsi-ld:Machine:cnc-01"
    assert entity["isPartOf"]["object"] == "urn:ngsi-ld:ProductionLine:line-t"
    assert entity["spindle_vib_rms"] == {
        "type": "Property",
        "value": 2.31,
        "unitCode": "C16",
        "observedAt": "2026-09-17T10:00:00Z",
    }
    assert "motor_current" not in entity, "sensors without readings are omitted (NGSI-LD has no null values)"


def test_plant_timezone_is_validated(client: TestClient) -> None:
    resp = client.post(
        f"{API}/plants", json={"code": "p2", "name": "P2", "timezone": "Mars/Base"}, headers=auth("admin")
    )
    assert resp.status_code == 422


def test_failure_modes_filter(client: TestClient, session: Session) -> None:
    from app.modules.assets.models import FailureMode

    session.add_all(
        [
            FailureMode(asset_type="cnc_mill", code="tool_wear", name="Tool wear", signature={"metrics": []}),
            FailureMode(asset_type="compressor", code="valve_leak", name="Valve leak", signature={"metrics": []}),
        ]
    )
    session.flush()
    modes = client.get(f"{API}/failure-modes", params={"asset_type": "cnc_mill"}, headers=auth("technician")).json()
    assert [m["code"] for m in modes] == ["tool_wear"]


def test_snapshot_serialises_dates_and_decimals(session: Session, seeded_asset: dict[str, Any]) -> None:
    from app.core.audit import snapshot

    asset = session.get(Asset, uuid.UUID(seeded_asset["id"]))
    assert asset is not None
    asset.install_date = date(2024, 1, 2)
    snap = snapshot(asset)
    assert snap["install_date"] == "2024-01-02"
    assert snap["rated_power_kw"] == 15.0
