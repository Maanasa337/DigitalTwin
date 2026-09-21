"""Asset Administration Shell (AAS v3) rendering, AASX export and AASX import via basyx-python-sdk.

Nameplate and TechnicalData are stored (so imported packages keep their extra elements); OperationalData,
MaintenanceHistory and PredictiveMaintenance are rendered on read from the database and the live twin.
"""

import io
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from basyx.aas import model
from basyx.aas.adapter import aasx
from basyx.aas.adapter.json import AASToJsonEncoder, StrictAASFromJsonDecoder, object_store_to_json

from app.core.errors import UnprocessableError
from app.modules.assets.models import Asset, Component, Sensor
from app.modules.assets.schemas import ComponentSpec, SensorSpec

BASE_IRI = "https://twinvoice.dev"
NAMEPLATE = "Nameplate"
TECHNICAL_DATA = "TechnicalData"
OPERATIONAL_DATA = "OperationalData"
MAINTENANCE_HISTORY = "MaintenanceHistory"
PREDICTIVE_MAINTENANCE = "PredictiveMaintenance"
STORED_SUBMODELS = (NAMEPLATE, TECHNICAL_DATA)

SEMANTIC_IDS = {
    NAMEPLATE: "https://admin-shell.io/zvei/nameplate/2/0/Nameplate",
    TECHNICAL_DATA: "https://admin-shell.io/ZVEI/TechnicalData/Submodel/1/2",
    OPERATIONAL_DATA: f"{BASE_IRI}/aas/semantics/OperationalData/1/0",
    MAINTENANCE_HISTORY: f"{BASE_IRI}/aas/semantics/MaintenanceHistory/1/0",
    PREDICTIVE_MAINTENANCE: f"{BASE_IRI}/aas/semantics/PredictiveMaintenance/1/0",
}

_S, _D, _I = model.datatypes.String, model.datatypes.Double, model.datatypes.Int


def shell_id(code: str) -> str:
    return f"{BASE_IRI}/aas/{code}"


def global_asset_id(code: str) -> str:
    return f"{BASE_IRI}/assets/{code}"


def submodel_id(code: str, id_short: str) -> str:
    return f"{BASE_IRI}/aas/{code}/submodels/{id_short}"


def id_short_for(code: str) -> str:
    """idShort must start with a letter and contain only letters, digits, '_' or '-'."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", code)
    return safe if safe[:1].isalpha() else f"x_{safe}"


def _ref(iri: str) -> model.ExternalReference:
    return model.ExternalReference((model.Key(model.KeyTypes.GLOBAL_REFERENCE, iri),))


def _prop(id_short: str, value: Any, value_type: type = _S) -> model.Property:
    if value is not None and value_type is _S:
        value = str(value)
    elif value is not None and value_type is _D:
        value = float(value)
    return model.Property(id_short=id_short, value_type=value_type, value=value)


def _mlp(id_short: str, text: str | None) -> model.MultiLanguageProperty:
    return model.MultiLanguageProperty(
        id_short=id_short, value=model.MultiLanguageTextType({"en": text}) if text else None
    )


def _collection(id_short: str, elements: Sequence[model.SubmodelElement]) -> model.SubmodelElementCollection:
    return model.SubmodelElementCollection(id_short=id_short, value=elements)


def _submodel(code: str, id_short: str, elements: list[model.SubmodelElement]) -> model.Submodel:
    return model.Submodel(
        id_=submodel_id(code, id_short),
        id_short=id_short,
        semantic_id=_ref(SEMANTIC_IDS[id_short]),
        submodel_element=elements,
    )


def build_nameplate(asset: Asset) -> model.Submodel:
    return _submodel(
        asset.code,
        NAMEPLATE,
        [
            _prop("URIOfTheProduct", global_asset_id(asset.code)),
            _mlp("ManufacturerName", asset.manufacturer),
            _mlp("ManufacturerProductDesignation", asset.model),
            _prop("SerialNumber", asset.serial_no),
        ],
    )


def build_technical_data(asset: Asset) -> model.Submodel:
    return _submodel(
        asset.code,
        TECHNICAL_DATA,
        [
            _collection(
                "GeneralInformation",
                [
                    _prop("ManufacturerName", asset.manufacturer),
                    _prop("ManufacturerArticleNumber", asset.model),
                ],
            ),
            _collection(
                "TechnicalProperties",
                [
                    _prop("AssetType", asset.asset_type),
                    _prop("RatedPowerKw", asset.rated_power_kw, _D),
                    _prop("IdealCycleTimeS", asset.ideal_cycle_time_s, _D),
                    _prop("FidelityLevel", asset.fidelity_level, _I),
                    _prop("InstallDate", asset.install_date.isoformat() if asset.install_date else None),
                ],
            ),
        ],
    )


def _sensor_collection(sensor: Sensor, telemetry: dict[str, Any]) -> model.SubmodelElementCollection:
    live = telemetry.get(sensor.metric_name) or {}
    return _collection(
        id_short_for(sensor.metric_name),
        [
            _prop("Code", sensor.code),
            _prop("MetricName", sensor.metric_name),
            _prop("Name", sensor.name),
            _prop("Unit", sensor.unit),
            _prop("Kind", sensor.kind),
            _prop("SampleRateHz", sensor.sample_rate_hz, _D),
            *[_prop(label, getattr(sensor, attr), _D) for label, attr in _THRESHOLDS],
            _prop("CurrentValue", live.get("v"), _D),
            _prop("ObservedAt", live.get("t")),
        ],
    )


_THRESHOLDS = (
    ("MinValid", "min_valid"), ("MaxValid", "max_valid"), ("WarnLow", "warn_low"),
    ("WarnHigh", "warn_high"), ("AlarmLow", "alarm_low"), ("AlarmHigh", "alarm_high"),
)  # fmt: skip


def build_operational_data(
    asset: Asset, components: list[Component], sensors: list[Sensor], telemetry: dict[str, Any]
) -> model.Submodel:
    by_component: dict[Any, list[Sensor]] = {}
    for sensor in sensors:
        by_component.setdefault(sensor.component_id, []).append(sensor)
    component_elements = [
        _collection(
            id_short_for(c.code),
            [
                _prop("Code", c.code),
                _prop("Name", c.name),
                _prop("ComponentType", c.component_type),
                _prop("HealthWeight", c.health_weight, _D),
                _prop("PhysicsModel", c.physics_model),
                _prop("PhysicsParams", json.dumps(c.physics_params)),
                _collection("Sensors", [_sensor_collection(s, telemetry) for s in by_component.get(c.id, [])]),
            ],
        )
        for c in components
    ]
    return _submodel(
        asset.code,
        OPERATIONAL_DATA,
        [
            _prop("Status", asset.status),
            _collection("Components", component_elements),
            _collection("AssetSensors", [_sensor_collection(s, telemetry) for s in by_component.get(None, [])]),
        ],
    )


def build_maintenance_history(asset: Asset) -> model.Submodel:
    orders = model.SubmodelElementList(id_short="WorkOrders", type_value_list_element=model.SubmodelElementCollection)
    return _submodel(asset.code, MAINTENANCE_HISTORY, [orders])


def build_predictive_maintenance(asset: Asset, prediction: dict[str, Any]) -> model.Submodel:
    rul = prediction.get("rul") or {}
    return _submodel(
        asset.code,
        PREDICTIVE_MAINTENANCE,
        [
            _prop("HealthIndex", prediction.get("health_index"), _D),
            _collection(
                "RemainingUsefulLife",
                [
                    _prop("Point", rul.get("point"), _D),
                    _prop("Low", rul.get("low"), _D),
                    _prop("High", rul.get("high"), _D),
                    _prop("Unit", rul.get("unit")),
                    _prop("Coverage", rul.get("coverage"), _D),
                ],
            ),
            _prop("ConfidenceLabel", (prediction.get("confidence") or {}).get("label")),
            _prop("ModelVersion", prediction.get("model_version")),
            _prop("PredictedAt", prediction.get("time")),
            _prop("ExplanationRef", prediction.get("explanation_id")),
        ],
    )


def submodel_to_json(submodel: model.Submodel) -> dict[str, Any]:
    return json.loads(json.dumps(submodel, cls=AASToJsonEncoder))


def submodel_from_json(data: dict[str, Any]) -> model.Submodel:
    return json.loads(json.dumps(data), cls=StrictAASFromJsonDecoder)


def build_store(asset: Asset, submodels: list[model.Submodel]) -> model.DictIdentifiableStore:
    shell = model.AssetAdministrationShell(
        id_=asset.aas_id or shell_id(asset.code),
        id_short=id_short_for(asset.code),
        display_name=model.MultiLanguageNameType({"en": asset.name[:64]}),
        asset_information=model.AssetInformation(
            asset_kind=model.AssetKind.INSTANCE, global_asset_id=global_asset_id(asset.code)
        ),
        submodel={model.ModelReference.from_referable(sm) for sm in submodels},
    )
    return model.DictIdentifiableStore([shell, *submodels])


def environment_json(store: model.DictIdentifiableStore) -> dict[str, Any]:
    return json.loads(object_store_to_json(store))


def write_aasx(store: model.DictIdentifiableStore, aas_id: str) -> bytes:
    buffer = io.BytesIO()
    with aasx.AASXWriter(buffer) as writer:
        writer.write_aas(
            aas_ids=[aas_id],
            object_store=store,
            file_store=aasx.DictSupplementaryFileContainer(),
            write_json=True,
        )
    return buffer.getvalue()


@dataclass
class ImportedAsset:
    code: str
    name: str
    manufacturer: str | None = None
    product_model: str | None = None
    serial_no: str | None = None
    install_date: date | None = None
    rated_power_kw: float | None = None
    ideal_cycle_time_s: float | None = None
    fidelity_level: int = 2
    stored_submodels: dict[str, model.Submodel] = field(default_factory=dict)
    components: list[ComponentSpec] = field(default_factory=list)
    sensors: list[SensorSpec] = field(default_factory=list)


def _find(elements: Any, id_short: str) -> Any:
    return next((e for e in elements or () if e.id_short == id_short), None)


def _value(elements: Any, id_short: str) -> Any:
    element = _find(elements, id_short)
    if isinstance(element, model.MultiLanguageProperty):
        texts: Mapping[str, str] = element.value or {}
        return texts.get("en") or next(iter(texts.values()), None)
    return getattr(element, "value", None)


def _sensor_specs(collection: Any, component_code: str | None) -> list[SensorSpec]:
    specs = []
    for element in collection.value if collection is not None else ():
        v = element.value
        specs.append(
            SensorSpec(
                code=_value(v, "Code"),
                component_code=component_code,
                metric_name=_value(v, "MetricName"),
                name=_value(v, "Name"),
                unit=_value(v, "Unit"),
                kind=_value(v, "Kind"),
                sample_rate_hz=_value(v, "SampleRateHz") or 1.0,
                **{attr: _value(v, label) for label, attr in _THRESHOLDS},
            )
        )
    return specs


def read_aasx(data: bytes) -> ImportedAsset:
    store: model.DictIdentifiableStore = model.DictIdentifiableStore()
    try:
        with aasx.AASXReader(io.BytesIO(data), failsafe=False) as reader:
            reader.read_into(store, aasx.DictSupplementaryFileContainer())
    except Exception as exc:
        raise UnprocessableError(f"Not a readable AASX package: {exc}") from exc

    shells = [obj for obj in store if isinstance(obj, model.AssetAdministrationShell)]
    if not shells:
        raise UnprocessableError("AASX package contains no Asset Administration Shell")
    shell = shells[0]
    global_id = shell.asset_information.global_asset_id or shell.id
    code = re.sub(r"[^a-z0-9-]", "-", global_id.rstrip("/").rsplit("/", 1)[-1].lower()).strip("-")
    display: Mapping[str, str] = shell.display_name or {}
    imported = ImportedAsset(code=code, name=display.get("en") or shell.id_short or code)

    submodels = {sm.id_short: sm for ref in shell.submodel if isinstance(sm := ref.resolve(store), model.Submodel)}
    if nameplate := submodels.get(NAMEPLATE):
        imported.manufacturer = _value(nameplate.submodel_element, "ManufacturerName")
        imported.product_model = _value(nameplate.submodel_element, "ManufacturerProductDesignation")
        imported.serial_no = _value(nameplate.submodel_element, "SerialNumber")
        imported.stored_submodels[NAMEPLATE] = nameplate
    if technical := submodels.get(TECHNICAL_DATA):
        props = _value(technical.submodel_element, "TechnicalProperties")
        if props is not None:
            imported.rated_power_kw = _value(props, "RatedPowerKw")
            imported.ideal_cycle_time_s = _value(props, "IdealCycleTimeS")
            imported.fidelity_level = int(_value(props, "FidelityLevel") or 2)
            installed = _value(props, "InstallDate")
            imported.install_date = date.fromisoformat(installed) if installed else None
        imported.stored_submodels[TECHNICAL_DATA] = technical
    if operational := submodels.get(OPERATIONAL_DATA):
        for component in _value(operational.submodel_element, "Components") or ():
            v = component.value
            imported.components.append(
                ComponentSpec(
                    code=_value(v, "Code"),
                    name=_value(v, "Name"),
                    component_type=_value(v, "ComponentType"),
                    health_weight=_value(v, "HealthWeight") or 1.0,
                    physics_model=_value(v, "PhysicsModel"),
                    physics_params=json.loads(_value(v, "PhysicsParams") or "{}"),
                )
            )
            imported.sensors += _sensor_specs(_find(v, "Sensors"), _value(v, "Code"))
        imported.sensors += _sensor_specs(_find(operational.submodel_element, "AssetSensors"), None)
    return imported
