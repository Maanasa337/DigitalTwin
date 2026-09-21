import uuid

from sqlalchemy import select

from app.common.repository import CrudRepository
from app.modules.assets.models import AasSubmodel, Asset, Component, FailureMode, Line, Plant, Sensor


class PlantRepository(CrudRepository[Plant]):
    model = Plant
    sortable = frozenset({"code", "name", "created_at"})
    default_sort = "code"

    def get_by_code(self, code: str) -> Plant | None:
        return self.session.scalars(self._select().where(Plant.code == code)).first()


class LineRepository(CrudRepository[Line]):
    model = Line
    sortable = frozenset({"code", "name", "sequence", "created_at"})
    default_sort = "sequence"

    def get_by_code(self, plant_id: uuid.UUID, code: str) -> Line | None:
        return self.session.scalars(self._select().where(Line.plant_id == plant_id, Line.code == code)).first()


class AssetRepository(CrudRepository[Asset]):
    model = Asset
    sortable = frozenset({"code", "name", "asset_type", "status", "created_at", "updated_at"})
    default_sort = "code"

    def get_by_code(self, code: str) -> Asset | None:
        return self.session.scalars(self._select().where(Asset.code == code)).first()


class ComponentRepository(CrudRepository[Component]):
    model = Component
    sortable = frozenset({"code", "created_at"})
    default_sort = "code"

    def for_assets(self, asset_ids: list[uuid.UUID]) -> list[Component]:
        return self.all([Component.asset_id.in_(asset_ids)])


class SensorRepository(CrudRepository[Sensor]):
    model = Sensor
    sortable = frozenset({"metric_name", "created_at"})
    default_sort = "metric_name"


class AasSubmodelRepository(CrudRepository[AasSubmodel]):
    model = AasSubmodel

    def for_asset(self, asset_id: uuid.UUID) -> dict[str, AasSubmodel]:
        rows = self.session.scalars(select(AasSubmodel).where(AasSubmodel.asset_id == asset_id))
        return {row.id_short: row for row in rows}


class FailureModeRepository(CrudRepository[FailureMode]):
    model = FailureMode
    sortable = frozenset({"code", "asset_type"})
    default_sort = "code"

    def get_by_code(self, asset_type: str, code: str) -> FailureMode | None:
        return self.session.scalars(
            select(FailureMode).where(FailureMode.asset_type == asset_type, FailureMode.code == code)
        ).first()
