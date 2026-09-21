from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.ditto import DittoClient
from app.core.security import (
    WRITE_ROLES,
    CurrentUser,
    SecondFactor,
    get_current_user,
    get_second_factor,
    require_role,
)
from app.dependencies import get_command_sender, get_ditto, get_simulator
from app.modules.simulation.client import SimulatorClient
from app.modules.twin.schemas import (
    CommandRequest,
    CommandResult,
    TwinOut,
    TwinTree,
    WhatIfRequest,
    WhatIfResult,
)
from app.modules.twin.service import CommandSender, TwinService
from app.modules.twin.whatif_service import WhatIfService

router = APIRouter(prefix="/twin", tags=["twin"])


def twin_service(session: Session = Depends(get_session), ditto: DittoClient = Depends(get_ditto)) -> TwinService:
    return TwinService(session, ditto)


@router.get("/tree", response_model=TwinTree, dependencies=[Depends(get_current_user)])
def twin_tree(service: TwinService = Depends(twin_service)) -> Any:
    return service.tree()


@router.get("/{code}", response_model=TwinOut, dependencies=[Depends(get_current_user)])
def get_twin(code: str, service: TwinService = Depends(twin_service)) -> Any:
    return service.get_twin(code)


@router.post("/{code}/commands", response_model=CommandResult)
def send_command(
    code: str,
    request: CommandRequest = Body(...),
    user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
    service: TwinService = Depends(twin_service),
    settings: Settings = Depends(get_settings),
    second_factor: SecondFactor = Depends(get_second_factor),
    sender: CommandSender = Depends(get_command_sender),
) -> Any:
    return service.send_command(
        user,
        code,
        request,
        allow_t3=settings.allow_t3,
        second_factor=second_factor,
        sender=sender,
        timeout_s=settings.command_ack_timeout_s,
    )


@router.post("/{code}/what-if", response_model=WhatIfResult, dependencies=[Depends(get_current_user)])
def run_what_if(
    code: str,
    request: WhatIfRequest = Body(default_factory=WhatIfRequest),
    service: TwinService = Depends(twin_service),
    session: Session = Depends(get_session),
    simulator: SimulatorClient = Depends(get_simulator),
) -> Any:
    """Project the asset's remaining life under a hypothetical operating point.

    Risk tier T1: the twin state is cloned and nothing is written back, so the answer is
    hypothetical by construction and needs no confirmation.
    """
    asset = service.get_asset_by_code(code)
    return WhatIfService(session, simulator).run(asset, request)
