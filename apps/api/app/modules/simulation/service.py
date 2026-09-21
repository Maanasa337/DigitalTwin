from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.audit import snapshot, write_audit
from app.core.errors import NotFoundError
from app.core.security import CurrentUser
from app.modules.assets.models import Asset
from app.modules.assets.repository import AssetRepository
from app.modules.simulation.client import SimulatorClient
from app.modules.simulation.models import Scenario, ScenarioRun
from app.modules.simulation.schemas import (
    ExportRequest,
    FaultInjection,
    ResetRequest,
    ScenarioStart,
    TimeScale,
)

EXPORT_TIMEOUT_S = 600


class SimulationService:
    """Authenticated, audited control of the simulator (M1). Simulator state itself is not stored here."""

    def __init__(self, session: Session, simulator: SimulatorClient) -> None:
        self.session = session
        self.simulator = simulator
        self.assets = AssetRepository(session)

    def _asset(self, code: str) -> Asset:
        asset = self.assets.get_by_code(code)
        if asset is None:
            raise NotFoundError(f"Asset '{code}' not found")
        return asset

    def status(self) -> Any:
        return self.simulator.request("GET", "/status")

    def scenarios(self) -> list[Scenario]:
        return list(self.session.scalars(select(Scenario).order_by(Scenario.code)))

    def start_scenario(self, actor: CurrentUser, data: ScenarioStart) -> Any:
        if self.session.get(Scenario, data.scenario_code) is None:
            raise NotFoundError(f"Scenario '{data.scenario_code}' not found")
        result = self.simulator.request("POST", "/scenario", json=data.model_dump())
        self.session.execute(
            update(ScenarioRun)
            .where(ScenarioRun.ended_at.is_(None), ScenarioRun.export_uri.is_(None))
            .values(ended_at=func.now())
        )
        run = ScenarioRun(scenario_code=data.scenario_code, time_scale=result["time_scale"], seed=result.get("seed"))
        self.session.add(run)
        self.session.flush()
        write_audit(
            self.session,
            actor=actor,
            entity="scenario_runs",
            entity_id=run.id,
            action="create",
            after=snapshot(run),
        )
        self.session.commit()
        return result

    def inject_fault(self, actor: CurrentUser, data: FaultInjection) -> Any:
        asset = self._asset(data.asset)
        result = self.simulator.request("POST", "/faults", json=data.model_dump())
        write_audit(
            self.session,
            actor=actor,
            entity="assets",
            entity_id=asset.id,
            action="inject_fault",
            after=data.model_dump(),
        )
        self.session.commit()
        return result

    def set_time_scale(self, actor: CurrentUser, data: TimeScale) -> Any:
        result = self.simulator.request("POST", "/time-scale", json=data.model_dump())
        write_audit(self.session, actor=actor, entity="simulation", entity_id=None, action="time_scale", after=result)
        self.session.commit()
        return result

    def reset(self, actor: CurrentUser, code: str, data: ResetRequest) -> Any:
        asset = self._asset(code)
        result = self.simulator.request("POST", f"/reset/{code}", json=data.model_dump())
        write_audit(self.session, actor=actor, entity="assets", entity_id=asset.id, action="reset", after=result)
        self.session.commit()
        return result

    def export(self, actor: CurrentUser, data: ExportRequest) -> Any:
        if data.scenario_code and self.session.get(Scenario, data.scenario_code) is None:
            raise NotFoundError(f"Scenario '{data.scenario_code}' not found")
        result = self.simulator.request("POST", "/export", json=data.model_dump(), timeout=EXPORT_TIMEOUT_S)
        run = ScenarioRun(
            scenario_code=data.scenario_code, seed=data.seed, export_uri=result["path"], ended_at=func.now()
        )
        self.session.add(run)
        self.session.flush()
        write_audit(
            self.session,
            actor=actor,
            entity="scenario_runs",
            entity_id=run.id,
            action="export",
            after={**data.model_dump(), "path": result["path"], "rows": result.get("rows")},
        )
        self.session.commit()
        return result
