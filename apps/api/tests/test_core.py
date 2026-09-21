import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.errors import UnauthorizedError
from app.core.security import TokenVerifier
from app.core.ws_hub import WsHub, channel_to_topic, to_client_message
from tests.conftest import FakeDitto, FakeSimulator, auth

API = "/api/v1"
ISSUER = "http://localhost:8081/realms/twinvoice"


class _Key:
    def __init__(self, key: Any) -> None:
        self.key = key


@pytest.fixture
def signer() -> tuple[TokenVerifier, Any]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = TokenVerifier("http://unused/certs", ISSUER, "twinvoice-api")
    verifier._jwks.get_signing_key_from_jwt = lambda token: _Key(private.public_key())  # type: ignore[method-assign]
    return verifier, private


def _token(private: Any, **claims: Any) -> str:
    now = int(time.time())
    body = {
        "sub": "u-1", "iss": ISSUER, "aud": ["twinvoice-api", "account"], "iat": now, "exp": now + 300,
        "name": "Marcus Engineer", "realm_access": {"roles": ["engineer", "default-roles-twinvoice", "offline_access"]},
        **claims,
    }  # fmt: skip
    return jwt.encode(body, private, algorithm="RS256")


def test_token_verifier_accepts_valid_keycloak_token_and_keeps_known_roles(signer: tuple[TokenVerifier, Any]) -> None:
    verifier, private = signer
    user = verifier.verify(_token(private))
    assert (user.sub, user.name, user.roles) == ("u-1", "Marcus Engineer", frozenset({"engineer"}))


@pytest.mark.parametrize(
    "claims",
    [{"aud": "account"}, {"iss": "http://evil/realms/twinvoice"}, {"exp": int(time.time()) - 10}],
    ids=["wrong-audience", "wrong-issuer", "expired"],
)
def test_token_verifier_rejects_bad_tokens(signer: tuple[TokenVerifier, Any], claims: dict[str, Any]) -> None:
    verifier, private = signer
    with pytest.raises(UnauthorizedError):
        verifier.verify(_token(private, **claims))


def test_token_signed_by_another_key_is_rejected(signer: tuple[TokenVerifier, Any]) -> None:
    verifier, _ = signer
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(UnauthorizedError):
        verifier.verify(_token(other))


def test_health_reports_each_dependency(client: TestClient, ditto: FakeDitto, simulator: FakeSimulator) -> None:
    ditto.available = False
    body = client.get(f"{API}/health").json()
    assert set(body["dependencies"]) == {"database", "valkey", "mqtt", "ditto", "keycloak", "simulator"}
    assert body["dependencies"]["database"]["ok"] is True
    assert body["dependencies"]["simulator"]["ok"] is True
    assert body["dependencies"]["ditto"]["ok"] is False
    assert body["status"] == "degraded"


def test_me_upserts_user(client: TestClient) -> None:
    first = client.get(f"{API}/me", headers=auth("manager")).json()
    second = client.get(f"{API}/me", headers=auth("manager")).json()
    assert first["id"] == second["id"]
    assert (first["sub"], first["roles"], first["locale"]) == ("sub-manager", ["manager"], "en")


def test_audit_lists_entity_history_with_actor_name(client: TestClient, seeded_asset: dict[str, Any]) -> None:
    client.patch(f"{API}/assets/{seeded_asset['id']}", json={"name": "Renamed"}, headers=auth("admin"))

    page = client.get(
        f"{API}/audit", params={"entity": "assets", "id": seeded_asset["id"]}, headers=auth("engineer")
    ).json()

    assert page["total"] == 2
    assert [(i["action"], i["actor_name"]) for i in page["items"]] == [("update", "Admin"), ("create", "Engineer")]
    assert client.get(f"{API}/audit", headers=auth("technician")).status_code == 403


def test_problem_details_and_request_id(client: TestClient) -> None:
    resp = client.get(f"{API}/does-not-exist", headers={"X-Request-ID": "req-123"})
    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/problem+json"
    assert resp.headers["x-request-id"] == "req-123"
    assert resp.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "instance": "/api/v1/does-not-exist",
    }


def test_metrics_endpoint(client: TestClient) -> None:
    client.get(f"{API}/health")
    assert "tv_http_requests_total" in client.get("/metrics").text


def test_live_socket_requires_valid_token(client: TestClient) -> None:
    for url in ("/ws/live", "/ws/live?token=bogus"):
        with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect(url) as ws:
            ws.receive_json()
        assert exc.value.code == 1008


def test_live_socket_subscription_receives_only_matching_topics(client: TestClient) -> None:
    hub = WsHub("redis://unused")
    client.app.state.ws_hub = hub  # type: ignore[attr-defined]
    raw = json.dumps({"kind": "telemetry", "payload": {"metrics": {"power_kw": {"v": 1.0, "u": "kW"}}}})
    with client.websocket_connect("/ws/live?token=technician") as ws:
        ws.send_json({"type": "subscribe", "topics": ["asset:cnc-01", "alarms", "bad topic!"]})
        assert ws.receive_json() == {"type": "subscribed", "topics": ["alarms", "asset:cnc-01"]}

        for topic in ("asset:cnc-02", "asset:cnc-01"):
            ws.portal.call(hub.publish_local, topic, to_client_message(topic, raw))
        assert ws.receive_json() == {
            "type": "telemetry",
            "asset": "cnc-01",
            "metrics": {"power_kw": {"v": 1.0, "u": "kW"}},
        }


def test_channel_mapping() -> None:
    assert channel_to_topic("live:cnc-01") == "asset:cnc-01"
    assert channel_to_topic("alarms") == "alarms"
    assert to_client_message("alarms", '{"kind": "alarm", "payload": {"id": "a1"}}') == {"type": "alarm", "id": "a1"}
