"""Process-wide clients created in the app lifespan, exposed as overridable FastAPI dependencies."""

from fastapi import Request

from app.core.ditto import DittoClient
from app.modules.simulation.client import SimulatorClient
from app.modules.twin.service import CommandSender, TwinSyncService


def get_ditto(request: Request) -> DittoClient:
    return request.app.state.ditto


def get_twin_sync(request: Request) -> TwinSyncService:
    return request.app.state.twin_sync


def get_command_sender(request: Request) -> CommandSender:
    return request.app.state.commands


def get_simulator(request: Request) -> SimulatorClient:
    return request.app.state.simulator
