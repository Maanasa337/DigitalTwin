import logging
import statistics
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.ditto import DittoClient
from app.core.errors import (
    ForbiddenError,
    GatewayTimeoutError,
    LockedError,
    NotFoundError,
    ProblemError,
)
from app.core.security import CurrentUser, SecondFactor
from app.modules.assets.models import Asset, Component, Line, Plant
from app.modules.assets.repository import (
    AssetRepository,
    ComponentRepository,
    LineRepository,
    PlantRepository,
)
from app.modules.twin import policies
from app.modules.twin.schemas import (
    CommandRequest,
    CommandResult,
    RulOut,
    TreeAsset,
    TreeComponent,
    TreeLine,
    TreePlant,
    TwinOut,
    TwinTree,
)

log = logging.getLogger(__name__)


class CommandSender(Protocol):
    def execute(
        self,
        asset_code: str,
        command: str,
        params: dict[str, Any],
        *,
        issued_by: str,
        tier: str,
        timeout_s: float,
    ) -> tuple[str, dict[str, Any] | None]: ...


def machine_health(components: list[tuple[float | None, float]]) -> float | None:
    """Machine health = min(component_health * weight) over components that report health (FR-DT-03)."""
    weighted = [health * weight for health, weight in components if health is not None]
    return round(min(weighted), 2) if weighted else None


def mean_health(values: list[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return round(statistics.fmean(known), 2) if known else None


class TwinSyncService:
    """Keeps Ditto things in step with the asset registry; called inside the asset transaction before commit."""

    def __init__(self, ditto: DittoClient) -> None:
        self.ditto = ditto
        self._policies_ready = False

    def ensure_policies(self) -> None:
        if not self._policies_ready:
            self.ditto.put_policy(policies.ACTIVE_POLICY_ID, policies.ACTIVE_POLICY)
            self.ditto.put_policy(policies.RETIRED_POLICY_ID, policies.RETIRED_POLICY)
            self._policies_ready = True

    @staticmethod
    def attributes(asset: Asset, line: Line, plant: Plant) -> dict[str, Any]:
        return {
            "code": asset.code,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "manufacturer": asset.manufacturer,
            "model": asset.model,
            "serial_no": asset.serial_no,
            "install_date": asset.install_date.isoformat() if asset.install_date else None,
            "fidelity_level": asset.fidelity_level,
            "aas_id": asset.aas_id,
            "line_code": line.code,
            "plant_code": plant.code,
        }

    def create_thing(self, asset: Asset, line: Line, plant: Plant, components: list[Component]) -> None:
        self.ensure_policies()
        self.ditto.put_thing(
            asset.ditto_thing_id,
            {
                "policyId": policies.ACTIVE_POLICY_ID,
                "attributes": self.attributes(asset, line, plant),
                "features": {
                    "telemetry": {"properties": {}},
                    "state": {"properties": {"status": asset.status}},
                    "prediction": {"properties": {}},
                    "components": {"properties": {c.code: {"health": None, "rul": None} for c in components}},
                },
            },
        )

    def update_thing(self, asset: Asset, line: Line, plant: Plant) -> None:
        self.ditto.merge_thing(
            asset.ditto_thing_id,
            {
                "attributes": self.attributes(asset, line, plant),
                "features": {"state": {"properties": {"status": asset.status}}},
            },
        )

    def add_component(self, asset: Asset, component: Component) -> None:
        self.ditto.merge_thing(
            asset.ditto_thing_id,
            {"features": {"components": {"properties": {component.code: {"health": None, "rul": None}}}}},
        )

    def retire_thing(self, asset: Asset) -> None:
        self.ensure_policies()
        self.ditto.set_policy_id(asset.ditto_thing_id, policies.RETIRED_POLICY_ID)


def _component_state(thing: dict[str, Any] | None) -> dict[str, Any]:
    if not thing:
        return {}
    return thing.get("features", {}).get("components", {}).get("properties", {}) or {}


class TwinService:
    def __init__(self, session: Session, ditto: DittoClient) -> None:
        self.session = session
        self.ditto = ditto
        self.plants = PlantRepository(session)
        self.lines = LineRepository(session)
        self.assets = AssetRepository(session)
        self.components = ComponentRepository(session)

    def get_asset_by_code(self, code: str) -> Asset:
        asset = self.assets.get_by_code(code)
        if asset is None:
            raise NotFoundError(f"Asset '{code}' not found")
        return asset

    def _things_by_id(self, thing_ids: list[str]) -> dict[str, dict[str, Any]]:
        try:
            return {t["thingId"]: t for t in self.ditto.get_things(thing_ids)}
        except ProblemError as exc:
            # The registry structure is still useful without live health; the UI shows "no data".
            log.warning("twin store unavailable for tree", extra={"error": exc.detail})
            return {}

    def tree(self) -> TwinTree:
        plants = self.plants.all()
        lines = self.lines.all()
        assets = self.assets.all()
        components = self.components.for_assets([a.id for a in assets])
        things = self._things_by_id([a.ditto_thing_id for a in assets])

        components_by_asset: dict[Any, list[Component]] = {}
        for c in components:
            components_by_asset.setdefault(c.asset_id, []).append(c)

        tree_assets_by_line: dict[Any, list[TreeAsset]] = {}
        for asset in assets:
            state = _component_state(things.get(asset.ditto_thing_id))
            tree_components = []
            weighted: list[tuple[float | None, float]] = []
            for c in components_by_asset.get(asset.id, []):
                live = state.get(c.code) or {}
                health = live.get("health")
                weighted.append((health, float(c.health_weight)))
                tree_components.append(
                    TreeComponent(
                        id=c.id,
                        code=c.code,
                        name=c.name,
                        component_type=c.component_type,
                        health=health,
                        rul=RulOut(**live["rul"]) if live.get("rul") else None,
                    )
                )
            tree_assets_by_line.setdefault(asset.line_id, []).append(
                TreeAsset(
                    id=asset.id,
                    code=asset.code,
                    name=asset.name,
                    asset_type=asset.asset_type,
                    status=asset.status,
                    fidelity_level=asset.fidelity_level,
                    health=machine_health(weighted),
                    components=tree_components,
                )
            )

        tree_lines_by_plant: dict[Any, list[TreeLine]] = {}
        for line in lines:
            line_assets = tree_assets_by_line.get(line.id, [])
            tree_lines_by_plant.setdefault(line.plant_id, []).append(
                TreeLine(
                    id=line.id,
                    code=line.code,
                    name=line.name,
                    health=mean_health([a.health for a in line_assets]),
                    assets=line_assets,
                )
            )

        return TwinTree(
            plants=[
                TreePlant(
                    id=p.id,
                    code=p.code,
                    name=p.name,
                    health=mean_health([line.health for line in tree_lines_by_plant.get(p.id, [])]),
                    lines=tree_lines_by_plant.get(p.id, []),
                )
                for p in plants
            ]
        )

    def get_twin(self, code: str) -> TwinOut:
        asset = self.get_asset_by_code(code)
        thing = self.ditto.get_thing(asset.ditto_thing_id)
        if thing is None:
            raise NotFoundError(f"Twin '{asset.ditto_thing_id}' does not exist in the twin store")
        components = self.components.for_assets([asset.id])
        state = _component_state(thing)
        return TwinOut(
            code=asset.code,
            asset_id=asset.id,
            thing_id=thing["thingId"],
            policy_id=thing.get("policyId"),
            revision=thing.get("_revision"),
            status=asset.status,
            fidelity_level=asset.fidelity_level,
            health=machine_health(
                [((state.get(c.code) or {}).get("health"), float(c.health_weight)) for c in components]
            ),
            attributes=thing.get("attributes", {}),
            features=thing.get("features", {}),
        )

    def send_command(
        self,
        actor: CurrentUser,
        code: str,
        request: CommandRequest,
        *,
        allow_t3: bool,
        second_factor: SecondFactor,
        sender: CommandSender,
        timeout_s: float,
    ) -> CommandResult:
        """Tier T3 write-back: server switch, asset check, PIN, publish, ack — audited whatever the outcome."""
        if not allow_t3:
            raise ForbiddenError("T3 write-back actions are disabled on this server (TV_ALLOW_T3=false)")
        asset = self.get_asset_by_code(code)
        if not request.pin or not second_factor.verify(actor.sub, request.pin):
            raise LockedError("A valid second factor (PIN) is required for T3 actions")

        params = request.params.model_dump()
        command_id, ack = sender.execute(
            asset.code, request.command, params, issued_by=actor.sub, tier="T3", timeout_s=timeout_s
        )
        outcome = ack["status"] if ack else "timeout"
        write_audit(
            self.session,
            actor=actor,
            entity="assets",
            entity_id=asset.id,
            action="execute",
            after={
                "command_id": command_id,
                "command": request.command,
                "params": params,
                "tier": "T3",
                "status": outcome,
                "error": ack.get("error") if ack else None,
            },
        )
        self.session.commit()
        if ack is None:
            raise GatewayTimeoutError(f"{asset.code} did not acknowledge command {command_id} within {timeout_s:g} s")
        return CommandResult(
            command_id=command_id, command=request.command, status=ack["status"], error=ack.get("error")
        )
