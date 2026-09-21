"""Service/API tests run against a real PostgreSQL+Timescale test database (compose `postgres`, db `twinvoice_test`).

External systems (Ditto, Keycloak, MQTT, simulator) are replaced by in-memory fakes at the dependency boundary.
"""

import copy
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, ClassVar

os.environ.setdefault("TV_DATABASE_URL", "postgresql+psycopg://twinvoice:twinvoice@127.0.0.1:5433/twinvoice_test")

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import BadGatewayError, ServiceUnavailableError, UnauthorizedError
from app.core.security import CurrentUser, get_second_factor, get_token_verifier
from app.main import create_app
from app.modules.simulation.client import SimulatorClient
from app.modules.twin import policies
from app.modules.twin.service import TwinSyncService

API_DIR = Path(__file__).resolve().parents[1]

USERS = {
    role: CurrentUser(sub=f"sub-{role}", name=role.title(), email=f"{role}@test", roles=frozenset({role}))
    for role in ("technician", "manager", "engineer", "admin")
}


def auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {role}"}


class FakeVerifier:
    def verify(self, token: str) -> CurrentUser:
        if token not in USERS:
            raise UnauthorizedError("Invalid or expired token")
        return USERS[token]

    def ping(self) -> None:
        pass


class FakeSecondFactor:
    pins: ClassVar[dict[str, str]] = {"sub-engineer": "246810", "sub-admin": "135790"}

    def verify(self, sub: str, pin: str) -> bool:
        return self.pins.get(sub) == pin


def _merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


class FakeDitto:
    """Enough of Ditto's behaviour to test sync: things, shared policies, merge patch, read-only retired policy."""

    def __init__(self) -> None:
        self.things: dict[str, dict[str, Any]] = {}
        self.policies: dict[str, dict[str, Any]] = {}
        self.available = True

    def _check(self) -> None:
        if not self.available:
            raise ServiceUnavailableError("Twin store (Ditto) unreachable")

    def _writable(self, thing_id: str) -> dict[str, Any]:
        thing = self.things[thing_id]
        if thing["policyId"] == policies.RETIRED_POLICY_ID:
            raise BadGatewayError("Twin store rejected write: not allowed")
        return thing

    def ping(self) -> None:
        self._check()

    def put_policy(self, policy_id: str, policy: dict[str, Any]) -> None:
        self._check()
        self.policies[policy_id] = policy

    def put_thing(self, thing_id: str, thing: dict[str, Any]) -> None:
        self._check()
        if thing_id in self.things:
            self._writable(thing_id)
        if thing["policyId"] not in self.policies:
            raise BadGatewayError("policy not found")
        self.things[thing_id] = {"thingId": thing_id, "_revision": 1, **copy.deepcopy(thing)}

    def get_thing(self, thing_id: str) -> dict[str, Any] | None:
        self._check()
        return copy.deepcopy(self.things.get(thing_id))

    def get_things(self, thing_ids: list[str]) -> list[dict[str, Any]]:
        self._check()
        return [copy.deepcopy(self.things[t]) for t in thing_ids if t in self.things]

    def merge_thing(self, thing_id: str, patch: dict[str, Any]) -> None:
        self._check()
        thing = self._writable(thing_id)
        _merge(thing, patch)
        thing["_revision"] += 1

    def set_policy_id(self, thing_id: str, policy_id: str) -> None:
        self._check()
        self._writable(thing_id)["policyId"] = policy_id

    def set_live(self, code: str, feature: str, properties: dict[str, Any]) -> None:
        self.things[policies.thing_id(code)]["features"][feature] = {"properties": properties}


class FakeCommands:
    def __init__(self) -> None:
        self.connected = True
        self.sent: list[dict[str, Any]] = []
        self.reply: Callable[[dict[str, Any]], dict[str, Any] | None] = lambda cmd: {
            "command_id": cmd["command_id"],
            "status": "accepted",
            "error": None,
        }

    def execute(
        self, asset_code: str, command: str, params: dict[str, Any], *, issued_by: str, tier: str, timeout_s: float
    ) -> tuple[str, dict[str, Any] | None]:
        cmd = {"command_id": f"cmd-{len(self.sent) + 1}", "asset": asset_code, "command": command, "params": params}
        self.sent.append(cmd)
        return cmd["command_id"], self.reply(cmd)


class FakeSimulator:
    """Routes httpx requests to canned handlers; unset routes answer 404 like the real simulator."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.up = True
        self.routes: dict[tuple[str, str], Callable[[Any], httpx.Response]] = {
            ("GET", "/health"): lambda _: httpx.Response(200, json={"status": "ok"}),
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("connection refused", request=request)
        body = request.read()
        payload = httpx.Response(200, content=body).json() if body else None
        self.calls.append((request.method, request.url.path, payload))
        route = self.routes.get((request.method, request.url.path))
        return route(payload) if route else httpx.Response(404, json={"detail": "not found"})


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = os.environ["TV_DATABASE_URL"]
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield db
    db.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def ditto() -> FakeDitto:
    return FakeDitto()


@pytest.fixture
def commands() -> FakeCommands:
    return FakeCommands()


@pytest.fixture
def simulator() -> FakeSimulator:
    return FakeSimulator()


@pytest.fixture
def settings() -> Settings:
    return Settings(allow_t3=True, command_ack_timeout_s=0.1)


@pytest.fixture
def client(
    session: Session, ditto: FakeDitto, commands: FakeCommands, simulator: FakeSimulator, settings: Settings
) -> Iterator[TestClient]:
    app = create_app()
    app.state.ditto = ditto
    app.state.twin_sync = TwinSyncService(ditto)  # type: ignore[arg-type]
    app.state.commands = commands
    app.state.simulator = SimulatorClient("http://simulator", transport=httpx.MockTransport(simulator.handler))

    def request_session() -> Iterator[Session]:
        try:
            yield session
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[get_session] = request_session
    app.dependency_overrides[get_token_verifier] = FakeVerifier
    app.dependency_overrides[get_second_factor] = FakeSecondFactor
    app.dependency_overrides[get_settings] = lambda: settings
    # No context manager: the lifespan (real MQTT/Valkey connections) must not run in tests.
    yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def plant_line(client: TestClient) -> dict[str, Any]:
    plant = client.post("/api/v1/plants", json={"code": "plant-t", "name": "Test Plant"}, headers=auth("engineer"))
    assert plant.status_code == 201, plant.text
    line = client.post(
        "/api/v1/lines",
        json={"plant_id": plant.json()["id"], "code": "line-t", "name": "Test Line"},
        headers=auth("engineer"),
    )
    assert line.status_code == 201, line.text
    return {"plant": plant.json(), "line": line.json()}


SAMPLE_COMPONENTS = [
    {"code": "spindle", "name": "Spindle", "component_type": "spindle", "health_weight": 1.0, "physics_model": "paris"},
    {"code": "motor", "name": "Motor", "component_type": "motor", "health_weight": 0.8, "physics_model": "none"},
]
SAMPLE_SENSORS = [
    {
        "code": "vib_rms", "component_code": "spindle", "metric_name": "spindle.vib_rms", "name": "Spindle vibration",
        "unit": "mm/s", "kind": "vibration", "warn_high": 4.5, "alarm_high": 7.1,
    },
    {
        "code": "current", "component_code": "motor", "metric_name": "motor.current", "name": "Motor current",
        "unit": "A", "kind": "current",
    },
    {"code": "power_kw", "component_code": None, "metric_name": "power_kw", "name": "Power", "unit": "kW", "kind": "power"},
]  # fmt: skip


@pytest.fixture
def seeded_asset(session: Session, ditto: FakeDitto, plant_line: dict[str, Any]) -> dict[str, Any]:
    """An asset with components and sensors, created the way seed/clone/import create them."""
    import uuid

    from app.modules.assets.schemas import AssetCreate, ComponentSpec, SensorSpec
    from app.modules.assets.service import AssetService

    asset = AssetService(session, TwinSyncService(ditto)).create_asset(  # type: ignore[arg-type]
        USERS["engineer"],
        AssetCreate(
            line_id=uuid.UUID(plant_line["line"]["id"]),
            code="cnc-01",
            name="CNC Mill 01",
            asset_type="cnc_mill",
            manufacturer="Acme",
            model="VMC-850",
            serial_no="SN-1",
            rated_power_kw=15,
            fidelity_level=3,
        ),
        components=[ComponentSpec(**c) for c in SAMPLE_COMPONENTS],
        sensors=[SensorSpec(**s) for s in SAMPLE_SENSORS],
    )
    return {"id": str(asset.id), "code": asset.code, "line_id": plant_line["line"]["id"]}
