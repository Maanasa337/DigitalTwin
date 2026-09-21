from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import WRITE_ROLES, CurrentUser, require_role
from app.dependencies import get_simulator
from app.modules.simulation.client import SimulatorClient
from app.modules.simulation.schemas import (
    ExportRequest,
    FaultInjection,
    ResetRequest,
    ScenarioOut,
    ScenarioStart,
    TimeScale,
)
from app.modules.simulation.service import SimulationService

router = APIRouter(prefix="/simulation", tags=["simulation"])
engineer = Depends(require_role(*WRITE_ROLES))


def simulation_service(
    session: Session = Depends(get_session), simulator: SimulatorClient = Depends(get_simulator)
) -> SimulationService:
    return SimulationService(session, simulator)


@router.get("/status", dependencies=[engineer])
def simulation_status(service: SimulationService = Depends(simulation_service)) -> Any:
    return service.status()


@router.get("/scenarios", response_model=list[ScenarioOut], dependencies=[engineer])
def list_scenarios(service: SimulationService = Depends(simulation_service)) -> Any:
    return service.scenarios()


@router.post("/scenario")
def start_scenario(
    data: ScenarioStart,
    user: CurrentUser = engineer,
    service: SimulationService = Depends(simulation_service),
) -> Any:
    return service.start_scenario(user, data)


@router.post("/faults")
def inject_fault(
    data: FaultInjection,
    user: CurrentUser = engineer,
    service: SimulationService = Depends(simulation_service),
) -> Any:
    return service.inject_fault(user, data)


@router.post("/time-scale")
def set_time_scale(
    data: TimeScale, user: CurrentUser = engineer, service: SimulationService = Depends(simulation_service)
) -> Any:
    return service.set_time_scale(user, data)


@router.post("/reset/{asset}")
def reset_asset(
    asset: str,
    data: ResetRequest = Body(default_factory=ResetRequest),
    user: CurrentUser = engineer,
    service: SimulationService = Depends(simulation_service),
) -> Any:
    return service.reset(user, asset, data)


@router.post("/export")
def export_dataset(
    data: ExportRequest,
    user: CurrentUser = engineer,
    service: SimulationService = Depends(simulation_service),
) -> Any:
    return service.export(user, data)
