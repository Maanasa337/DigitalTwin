from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, WebSocket, status
from prometheus_client import make_asgi_app
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.ditto import DittoClient
from app.core.errors import ProblemError, UnauthorizedError, register_error_handlers
from app.core.observability import RequestContextMiddleware, configure_logging
from app.core.router import router as core_router
from app.core.security import TokenVerifier, get_token_verifier
from app.core.ws_hub import WsHub
from app.modules.analytics.router import router as analytics_router
from app.modules.assets.router import router as assets_router
from app.modules.maintenance.router import router as maintenance_router
from app.modules.pdm.router import router as pdm_router
from app.modules.reports.router import router as reports_router
from app.modules.simulation.client import SimulatorClient
from app.modules.simulation.router import router as simulation_router
from app.modules.telemetry.router import router as telemetry_router
from app.modules.twin.commands import CommandGateway
from app.modules.twin.router import router as twin_router
from app.modules.twin.service import TwinSyncService
from app.modules.voice.router import router as voice_router
from app.modules.xai.router import router as xai_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.ditto = DittoClient(settings.ditto_url, settings.ditto_subject)
    app.state.twin_sync = TwinSyncService(app.state.ditto)
    app.state.simulator = SimulatorClient(settings.simulator_url)
    app.state.commands = CommandGateway(settings.mqtt_host, settings.mqtt_port)
    app.state.commands.start()
    app.state.ws_hub = WsHub(settings.valkey_url)
    await app.state.ws_hub.start()
    try:
        yield
    finally:
        await app.state.ws_hub.stop()
        app.state.commands.stop()
        app.state.simulator.close()
        app.state.ditto.close()


def create_app() -> FastAPI:
    app = FastAPI(title="TwinVoice API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    api = APIRouter(prefix="/api/v1")
    routers = (
        core_router,
        assets_router,
        twin_router,
        simulation_router,
        telemetry_router,
        pdm_router,
        xai_router,
        maintenance_router,
        analytics_router,
        voice_router,
        reports_router,
    )
    for router in routers:
        api.include_router(router)
    app.include_router(api)
    app.mount("/metrics", make_asgi_app())

    @app.websocket("/ws/live")
    async def live(
        websocket: WebSocket,
        token: str | None = None,
        verifier: TokenVerifier = Depends(get_token_verifier),
    ) -> None:
        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        try:
            await run_in_threadpool(verifier.verify, token)
        except UnauthorizedError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        except ProblemError:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return
        await websocket.accept()
        await app.state.ws_hub.handle(websocket)

    return app


app = create_app()
