import logging
import re
import uuid
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.common.service import CrudService
from app.core.audit import snapshot, write_audit
from app.core.errors import ConflictError, NotFoundError, ProblemError, UnprocessableError
from app.core.security import CurrentUser
from app.modules.assets import aas
from app.modules.assets.adapters import to_dtdl, to_ngsi_ld
from app.modules.assets.models import AasSubmodel, Asset, Component, FailureMode, Line, Plant, Sensor
from app.modules.assets.repository import (
    AasSubmodelRepository,
    AssetRepository,
    ComponentRepository,
    FailureModeRepository,
    LineRepository,
    PlantRepository,
    SensorRepository,
)
from app.modules.assets.schemas import (
    CODE_PATTERN,
    AssetClone,
    AssetCreate,
    AssetUpdate,
    ComponentCreate,
    ComponentSpec,
    LineCreate,
    PlantCreate,
    SensorSpec,
)
from app.modules.twin.policies import thing_id
from app.modules.twin.service import TwinSyncService

log = logging.getLogger(__name__)

_STATIC_BUILDERS = {aas.NAMEPLATE: aas.build_nameplate, aas.TECHNICAL_DATA: aas.build_technical_data}


class PlantService(CrudService[Plant]):
    entity, label = "plants", "Plant"

    def __init__(self, session: Session) -> None:
        super().__init__(session, PlantRepository(session))
        self.plants = PlantRepository(session)

    def create_plant(self, actor: CurrentUser | None, data: PlantCreate) -> Plant:
        if self.plants.get_by_code(data.code):
            raise ConflictError(f"Plant code '{data.code}' already exists")
        return self.create(actor, Plant(**data.model_dump()))


class LineService(CrudService[Line]):
    entity, label = "lines", "Line"

    def __init__(self, session: Session) -> None:
        super().__init__(session, LineRepository(session))
        self.lines = LineRepository(session)

    def create_line(self, actor: CurrentUser | None, data: LineCreate) -> Line:
        if PlantRepository(self.session).get(data.plant_id) is None:
            raise UnprocessableError(f"Plant {data.plant_id} does not exist")
        if self.lines.get_by_code(data.plant_id, data.code):
            raise ConflictError(f"Line code '{data.code}' already exists in this plant")
        return self.create(actor, Line(**data.model_dump()))


class AssetService(CrudService[Asset]):
    entity, label = "assets", "Asset"

    def __init__(self, session: Session, twin_sync: TwinSyncService) -> None:
        super().__init__(session, AssetRepository(session))
        self.assets = AssetRepository(session)
        self.components = ComponentRepository(session)
        self.sensors = SensorRepository(session)
        self.submodels = AasSubmodelRepository(session)
        self.twin_sync = twin_sync

    def list_assets(
        self,
        params: PageParams,
        *,
        line_id: uuid.UUID | None,
        asset_type: str | None,
        status: str | None,
        q: str | None,
    ) -> tuple[list[Asset], int]:
        filters = []
        if line_id:
            filters.append(Asset.line_id == line_id)
        if asset_type:
            filters.append(Asset.asset_type == asset_type)
        if status:
            filters.append(Asset.status == status)
        if q:
            pattern = f"%{q.replace('%', r'\%').replace('_', r'\_')}%"
            filters.append(Asset.code.ilike(pattern) | Asset.name.ilike(pattern))
        return self.assets.list(params, filters)

    def _line_and_plant(self, line_id: uuid.UUID) -> tuple[Line, Plant]:
        line = LineRepository(self.session).get(line_id)
        if line is None:
            raise UnprocessableError(f"Line {line_id} does not exist")
        plant = self.session.get(Plant, line.plant_id)
        assert plant is not None
        return line, plant

    def _assert_code_free(self, code: str) -> None:
        if self.assets.get_by_code(code):
            raise ConflictError(f"Asset code '{code}' already exists")
        # Ditto keeps retired twins read-only under the same thing id, so their codes cannot be reused.
        if self.session.scalar(select(exists().where(Asset.code == code, Asset.deleted_at.is_not(None)))):
            raise ConflictError(f"Asset code '{code}' belongs to a retired twin; choose another code")

    def create_asset(
        self,
        actor: CurrentUser | None,
        data: AssetCreate,
        *,
        components: Sequence[ComponentSpec] = (),
        sensors: Sequence[SensorSpec] = (),
        stored_submodels: dict[str, Any] | None = None,
    ) -> Asset:
        line, plant = self._line_and_plant(data.line_id)
        self._assert_code_free(data.code)
        asset = Asset(
            **data.model_dump(exclude={"position"}),
            position=data.position.model_dump() if data.position else None,
            ditto_thing_id=thing_id(data.code),
            aas_id=aas.shell_id(data.code),
        )
        self.assets.create(asset)
        created = self._add_structure(asset, components, sensors)
        self._store_submodels(asset, stored_submodels or {})
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=asset.id,
            action="create",
            after={**snapshot(asset), "components": [c.code for c in created], "sensor_count": len(sensors)},
        )
        self.twin_sync.create_thing(asset, line, plant, created)
        self.session.commit()
        return asset

    def _add_structure(
        self, asset: Asset, components: Sequence[ComponentSpec], sensors: Sequence[SensorSpec]
    ) -> list[Component]:
        created = [self.components.create(Component(asset_id=asset.id, **c.model_dump())) for c in components]
        ids = {c.code: c.id for c in created}
        for s in sensors:
            if s.component_code is not None and s.component_code not in ids:
                raise UnprocessableError(f"Sensor {s.metric_name} references unknown component '{s.component_code}'")
            self.sensors.create(
                Sensor(
                    asset_id=asset.id,
                    component_id=ids.get(s.component_code) if s.component_code else None,
                    **s.model_dump(exclude={"component_code"}),
                )
            )
        return created

    def _store_submodels(self, asset: Asset, overrides: dict[str, Any]) -> None:
        existing = self.submodels.for_asset(asset.id)
        for id_short, build in _STATIC_BUILDERS.items():
            content = aas.submodel_to_json(overrides.get(id_short) or build(asset))
            if row := existing.get(id_short):
                row.content = content
            else:
                self.session.add(
                    AasSubmodel(
                        asset_id=asset.id,
                        id_short=id_short,
                        semantic_id=aas.SEMANTIC_IDS[id_short],
                        content=content,
                    )
                )
        self.session.flush()

    def update_asset(self, actor: CurrentUser | None, asset: Asset, data: AssetUpdate) -> Asset:
        values = data.model_dump(exclude_unset=True)
        if "position" in values and data.position is not None:
            values["position"] = data.position.model_dump()
        before = snapshot(asset)
        self.assets.update(asset, values)
        self._store_submodels(asset, {})
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=asset.id,
            action="update",
            before=before,
            after=snapshot(asset),
        )
        self.twin_sync.update_thing(asset, *self._line_and_plant(asset.line_id))
        self.session.commit()
        return asset

    def retire_asset(self, actor: CurrentUser | None, asset: Asset) -> None:
        before = snapshot(asset)
        self.assets.soft_delete(asset)
        write_audit(self.session, actor=actor, entity=self.entity, entity_id=asset.id, action="delete", before=before)
        self.twin_sync.retire_thing(asset)
        self.session.commit()

    def clone_asset(self, actor: CurrentUser | None, source: Asset, data: AssetClone) -> Asset:
        components = self.components.for_assets([source.id])
        codes = {c.id: c.code for c in components}
        create = AssetCreate.model_validate(
            {
                **snapshot(source),
                "code": data.code,
                "name": data.name,
                "serial_no": None,
            }
        )
        return self.create_asset(
            actor,
            create,
            components=[ComponentSpec.model_validate(c, from_attributes=True) for c in components],
            sensors=[
                SensorSpec.model_validate(
                    {**snapshot(s), "component_code": codes.get(s.component_id) if s.component_id else None}
                )
                for s in self.sensors.all([Sensor.asset_id == source.id])
            ],
        )

    def import_aasx(self, actor: CurrentUser | None, content: bytes, line_id: uuid.UUID, asset_type: str) -> Asset:
        imported = aas.read_aasx(content)
        if not re.match(CODE_PATTERN, imported.code):
            raise UnprocessableError(f"Derived asset code '{imported.code}' is not valid; expected {CODE_PATTERN}")
        try:
            data = AssetCreate(
                line_id=line_id,
                code=imported.code,
                name=imported.name,
                asset_type=asset_type,  # type: ignore[arg-type]
                manufacturer=imported.manufacturer,
                model=imported.product_model,
                serial_no=imported.serial_no,
                install_date=imported.install_date,
                fidelity_level=imported.fidelity_level,
                ideal_cycle_time_s=imported.ideal_cycle_time_s,
                rated_power_kw=imported.rated_power_kw,
            )
        except ValidationError as exc:
            raise UnprocessableError(f"AASX content is not a valid asset: {exc.errors(include_url=False)}") from exc
        return self.create_asset(
            actor,
            data,
            components=imported.components,
            sensors=imported.sensors,
            stored_submodels=imported.stored_submodels,
        )

    def asset_components(self, asset_id: uuid.UUID) -> list[Component]:
        return self.components.for_assets([self.get_or_404(asset_id).id])

    def asset_sensors(self, asset_id: uuid.UUID) -> list[Sensor]:
        return self.sensors.all([Sensor.asset_id == self.get_or_404(asset_id).id])

    def _live_features(self, asset: Asset) -> dict[str, Any]:
        try:
            thing = self.twin_sync.ditto.get_thing(asset.ditto_thing_id) or {}
        except ProblemError as exc:
            log.warning("twin store unavailable; rendering without live values", extra={"error": exc.detail})
            thing = {}
        features = thing.get("features", {})
        return {name: (features.get(name) or {}).get("properties", {}) for name in ("telemetry", "prediction")}

    def aas_store(self, asset: Asset) -> Any:
        components = self.components.for_assets([asset.id])
        sensors = self.sensors.all([Sensor.asset_id == asset.id])
        live = self._live_features(asset)
        stored = self.submodels.for_asset(asset.id)
        submodels = [
            aas.submodel_from_json(stored[id_short].content) if id_short in stored else build(asset)
            for id_short, build in _STATIC_BUILDERS.items()
        ]
        submodels += [
            aas.build_operational_data(asset, components, sensors, live["telemetry"]),
            aas.build_maintenance_history(asset),
            aas.build_predictive_maintenance(asset, live["prediction"]),
        ]
        return aas.build_store(asset, submodels)

    def aas_environment(self, asset: Asset) -> dict[str, Any]:
        return aas.environment_json(self.aas_store(asset))

    def aasx(self, asset: Asset) -> bytes:
        return aas.write_aasx(self.aas_store(asset), asset.aas_id or aas.shell_id(asset.code))

    def dtdl(self, asset: Asset) -> dict[str, Any]:
        return to_dtdl(asset, self.components.for_assets([asset.id]), self.sensors.all([Sensor.asset_id == asset.id]))

    def ngsi_ld(self, asset: Asset) -> dict[str, Any]:
        line = self.session.get(Line, asset.line_id)
        assert line is not None
        return to_ngsi_ld(
            asset,
            line,
            self.components.for_assets([asset.id]),
            self.sensors.all([Sensor.asset_id == asset.id]),
            self._live_features(asset)["telemetry"],
        )


class ComponentService(CrudService[Component]):
    entity, label = "components", "Component"

    def __init__(self, session: Session, twin_sync: TwinSyncService) -> None:
        super().__init__(session, ComponentRepository(session))
        self.twin_sync = twin_sync

    def create_component(self, actor: CurrentUser | None, data: ComponentCreate) -> Component:
        asset = AssetRepository(self.session).get(data.asset_id)
        if asset is None:
            raise NotFoundError(f"Asset {data.asset_id} not found")
        if self.session.scalar(
            select(
                exists().where(
                    Component.asset_id == asset.id,
                    Component.code == data.code,
                    Component.deleted_at.is_(None),
                )
            )
        ):
            raise ConflictError(f"Component code '{data.code}' already exists on {asset.code}")
        component = self.repo.create(Component(**data.model_dump()))
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=component.id,
            action="create",
            after=snapshot(component),
        )
        self.twin_sync.add_component(asset, component)
        self.session.commit()
        return component


class FailureModeService:
    def __init__(self, session: Session) -> None:
        self.repo = FailureModeRepository(session)

    def list_modes(self, asset_type: str | None) -> list[FailureMode]:
        return self.repo.all([FailureMode.asset_type == asset_type] if asset_type else [])
