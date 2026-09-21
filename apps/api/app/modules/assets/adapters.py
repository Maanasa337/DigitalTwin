"""Interoperability views of the same twin: DTDL v3 interface and NGSI-LD entity (FR-DT-02)."""

import re
from typing import Any

from app.modules.assets.models import Asset, Component, Line, Sensor

NGSI_LD_CORE_CONTEXT = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld"

# UN/CEFACT common codes for the units the platform uses.
UNIT_CODES = {
    "°C": "CEL", "A": "AMP", "V": "VLT", "kW": "KWT", "kWh": "KWH", "bar": "BAR", "%": "P1",
    "mm/s": "C16", "m/s": "MTS", "L/min": "L2", "kN": "B47", "N·m": "NU", "Nm": "NU", "rpm": "RPM",
    "s": "SEC", "mm": "MMT", "mm/min": "H81", "count": "C62", "Hz": "HTZ",
}  # fmt: skip


def dtdl_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_")
    return name if name[:1].isalpha() else f"x_{name}"


def _dtmi(*segments: str) -> str:
    return "dtmi:" + ":".join(dtdl_name(s) for s in segments) + ";1"


def _telemetry(sensor: Sensor) -> dict[str, Any]:
    return {
        "@type": "Telemetry",
        "name": dtdl_name(sensor.code if sensor.component_id else sensor.metric_name),
        "displayName": sensor.name[:64],
        "description": f"{sensor.metric_name} [{sensor.unit}]",
        "schema": "double",
    }


def to_dtdl(asset: Asset, components: list[Component], sensors: list[Sensor]) -> dict[str, Any]:
    properties = [
        ("status", "string"), ("fidelityLevel", "integer"), ("manufacturer", "string"),
        ("model", "string"), ("serialNumber", "string"), ("ratedPowerKw", "double"),
    ]  # fmt: skip
    contents: list[dict[str, Any]] = [{"@type": "Property", "name": n, "schema": s} for n, s in properties]
    contents += [_telemetry(s) for s in sensors if s.component_id is None]
    for component in components:
        contents.append(
            {
                "@type": "Component",
                "name": dtdl_name(component.code),
                "displayName": component.name[:64],
                "schema": {
                    "@id": _dtmi("twinvoice", asset.code, component.code),
                    "@type": "Interface",
                    "contents": [
                        {"@type": "Property", "name": "health", "schema": "double"},
                        *[_telemetry(s) for s in sensors if s.component_id == component.id],
                    ],
                },
            }
        )
    return {
        "@context": "dtmi:dtdl:context;3",
        "@id": _dtmi("twinvoice", "asset", asset.code),
        "@type": "Interface",
        "displayName": asset.name[:64],
        "description": f"{asset.asset_type} {asset.code}",
        "contents": contents,
    }


def to_ngsi_ld(
    asset: Asset, line: Line, components: list[Component], sensors: list[Sensor], telemetry: dict[str, Any]
) -> dict[str, Any]:
    def prop(value: Any) -> dict[str, Any]:
        return {"type": "Property", "value": value}

    entity: dict[str, Any] = {
        "id": f"urn:ngsi-ld:Machine:{asset.code}",
        "type": "Machine",
        "name": prop(asset.name),
        "assetType": prop(asset.asset_type),
        "status": prop(asset.status),
        "fidelityLevel": prop(asset.fidelity_level),
        "isPartOf": {"type": "Relationship", "object": f"urn:ngsi-ld:ProductionLine:{line.code}"},
    }
    for key, value in (
        ("manufacturer", asset.manufacturer),
        ("model", asset.model),
        ("serialNumber", asset.serial_no),
    ):
        if value is not None:
            entity[key] = prop(value)
    if components:
        entity["hasComponent"] = [
            {
                "type": "Relationship",
                "object": f"urn:ngsi-ld:MachineComponent:{asset.code}.{c.code}",
                "datasetId": f"urn:ngsi-ld:Dataset:{c.code}",
            }
            for c in components
        ]
    # NGSI-LD properties cannot be null, so sensors appear once the twin has a reading for them.
    for sensor in sensors:
        live = telemetry.get(sensor.metric_name)
        if not live or live.get("v") is None:
            continue
        attribute: dict[str, Any] = {"type": "Property", "value": live["v"]}
        if code := UNIT_CODES.get(sensor.unit):
            attribute["unitCode"] = code
        if live.get("t"):
            attribute["observedAt"] = live["t"]
        entity[dtdl_name(sensor.metric_name)] = attribute
    entity["@context"] = [NGSI_LD_CORE_CONTEXT]
    return entity
