import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.common.pagination import PageParams, page_params
from app.common.schemas import Page
from app.core.db import get_session
from app.core.errors import UnprocessableError
from app.core.security import WRITE_ROLES, CurrentUser, get_current_user, require_role
from app.dependencies import get_twin_sync
from app.modules.assets.models import Line
from app.modules.assets.schemas import (
    AssetClone,
    AssetCreate,
    AssetOut,
    AssetStatus,
    AssetType,
    AssetUpdate,
    ComponentCreate,
    ComponentOut,
    FailureModeOut,
    LineCreate,
    LineOut,
    PlantCreate,
    PlantOut,
    SensorOut,
)
from app.modules.assets.service import (
    AssetService,
    ComponentService,
    FailureModeService,
    LineService,
    PlantService,
)
from app.modules.twin.service import TwinSyncService

router = APIRouter(tags=["assets"])
reader = Depends(get_current_user)
writer = Depends(require_role(*WRITE_ROLES))
MAX_AASX_BYTES = 20 * 1024 * 1024


def asset_service(
    session: Session = Depends(get_session), twin_sync: TwinSyncService = Depends(get_twin_sync)
) -> AssetService:
    return AssetService(session, twin_sync)


@router.get("/plants", response_model=Page[PlantOut], dependencies=[reader])
def list_plants(params: PageParams = Depends(page_params), session: Session = Depends(get_session)) -> Any:
    items, total = PlantService(session).repo.list(params)
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.post("/plants", response_model=PlantOut, status_code=status.HTTP_201_CREATED)
def create_plant(data: PlantCreate, user: CurrentUser = writer, session: Session = Depends(get_session)) -> Any:
    return PlantService(session).create_plant(user, data)


@router.get("/lines", response_model=Page[LineOut], dependencies=[reader])
def list_lines(
    plant_id: uuid.UUID | None = None,
    params: PageParams = Depends(page_params),
    session: Session = Depends(get_session),
) -> Any:
    items, total = LineService(session).repo.list(params, [Line.plant_id == plant_id] if plant_id else [])
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.post("/lines", response_model=LineOut, status_code=status.HTTP_201_CREATED)
def create_line(data: LineCreate, user: CurrentUser = writer, session: Session = Depends(get_session)) -> Any:
    return LineService(session).create_line(user, data)


@router.get("/assets", response_model=Page[AssetOut], dependencies=[reader])
def list_assets(
    line_id: uuid.UUID | None = None,
    asset_type: AssetType | None = None,
    status: AssetStatus | None = None,
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    service: AssetService = Depends(asset_service),
) -> Any:
    items, total = service.list_assets(params, line_id=line_id, asset_type=asset_type, status=status, q=q)
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.post("/assets", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
def create_asset(data: AssetCreate, user: CurrentUser = writer, service: AssetService = Depends(asset_service)) -> Any:
    return service.create_asset(user, data)


@router.post("/assets/import-aasx", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
def import_aasx(
    file: UploadFile = File(...),
    line_id: uuid.UUID = Form(...),
    asset_type: AssetType = Form(...),
    user: CurrentUser = writer,
    service: AssetService = Depends(asset_service),
) -> Any:
    content = file.file.read(MAX_AASX_BYTES + 1)
    if len(content) > MAX_AASX_BYTES:
        raise UnprocessableError("AASX file exceeds 20 MB")
    return service.import_aasx(user, content, line_id, asset_type)


@router.get("/assets/{asset_id}", response_model=AssetOut, dependencies=[reader])
def get_asset(asset_id: uuid.UUID, service: AssetService = Depends(asset_service)) -> Any:
    return service.get_or_404(asset_id)


@router.patch("/assets/{asset_id}", response_model=AssetOut)
def update_asset(
    asset_id: uuid.UUID,
    data: AssetUpdate,
    user: CurrentUser = writer,
    service: AssetService = Depends(asset_service),
) -> Any:
    return service.update_asset(user, service.get_or_404(asset_id), data)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_asset(
    asset_id: uuid.UUID, user: CurrentUser = writer, service: AssetService = Depends(asset_service)
) -> Response:
    service.retire_asset(user, service.get_or_404(asset_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/assets/{asset_id}/clone", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
def clone_asset(
    asset_id: uuid.UUID,
    data: AssetClone,
    user: CurrentUser = writer,
    service: AssetService = Depends(asset_service),
) -> Any:
    return service.clone_asset(user, service.get_or_404(asset_id), data)


@router.get("/assets/{asset_id}/components", response_model=list[ComponentOut], dependencies=[reader])
def asset_components(asset_id: uuid.UUID, service: AssetService = Depends(asset_service)) -> Any:
    return service.asset_components(asset_id)


@router.get("/assets/{asset_id}/sensors", response_model=list[SensorOut], dependencies=[reader])
def asset_sensors(asset_id: uuid.UUID, service: AssetService = Depends(asset_service)) -> Any:
    return service.asset_sensors(asset_id)


@router.get("/assets/{asset_id}/aas", dependencies=[reader])
def asset_aas(asset_id: uuid.UUID, service: AssetService = Depends(asset_service)) -> dict[str, Any]:
    return service.aas_environment(service.get_or_404(asset_id))


@router.get("/assets/{asset_id}/aas.aasx", dependencies=[reader], response_class=Response)
def asset_aasx(asset_id: uuid.UUID, service: AssetService = Depends(asset_service)) -> Response:
    asset = service.get_or_404(asset_id)
    return Response(
        service.aasx(asset),
        media_type="application/asset-administration-shell-package",
        headers={"Content-Disposition": f'attachment; filename="{asset.code}.aasx"'},
    )


@router.get("/assets/{asset_id}/dtdl", dependencies=[reader])
def asset_dtdl(asset_id: uuid.UUID, service: AssetService = Depends(asset_service)) -> dict[str, Any]:
    return service.dtdl(service.get_or_404(asset_id))


@router.get("/assets/{asset_id}/ngsi-ld", dependencies=[reader])
def asset_ngsi_ld(asset_id: uuid.UUID, service: AssetService = Depends(asset_service)) -> Response:
    return Response(json.dumps(service.ngsi_ld(service.get_or_404(asset_id))), media_type="application/ld+json")


@router.get("/components", response_model=list[ComponentOut], dependencies=[reader])
def list_components(asset_id: uuid.UUID, service: AssetService = Depends(asset_service)) -> Any:
    return service.asset_components(asset_id)


@router.post("/components", response_model=ComponentOut, status_code=status.HTTP_201_CREATED)
def create_component(
    data: ComponentCreate,
    user: CurrentUser = writer,
    session: Session = Depends(get_session),
    twin_sync: TwinSyncService = Depends(get_twin_sync),
) -> Any:
    return ComponentService(session, twin_sync).create_component(user, data)


@router.get("/failure-modes", response_model=list[FailureModeOut], dependencies=[reader])
def list_failure_modes(asset_type: AssetType | None = None, session: Session = Depends(get_session)) -> Any:
    return FailureModeService(session).list_modes(asset_type)
