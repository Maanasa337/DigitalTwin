"""Thin HTTP client for the Eclipse Ditto twin store (API v2, pre-authenticated subject)."""

import json
from typing import Any

import httpx

from app.core.errors import BadGatewayError, ServiceUnavailableError

MERGE_PATCH = "application/merge-patch+json"


class DittoClient:
    def __init__(
        self,
        base_url: str,
        subject: str,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/api/2",
            headers={"x-ditto-pre-authenticated": subject},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            resp = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError("Twin store (Ditto) unreachable") from exc
        if resp.status_code >= 400 and resp.status_code != 404:
            message = resp.json().get("message", resp.text) if resp.content else resp.reason_phrase
            raise BadGatewayError(f"Twin store rejected {method} {path}: {message}")
        return resp

    def ping(self) -> None:
        self._request("GET", "/whoami")

    def put_policy(self, policy_id: str, policy: dict[str, Any]) -> None:
        self._request("PUT", f"/policies/{policy_id}", json=policy)

    def put_thing(self, thing_id: str, thing: dict[str, Any]) -> None:
        self._request("PUT", f"/things/{thing_id}", json=thing)

    def get_thing(self, thing_id: str) -> dict[str, Any] | None:
        resp = self._request(
            "GET", f"/things/{thing_id}", params={"fields": "thingId,policyId,_revision,attributes,features"}
        )
        return None if resp.status_code == 404 else resp.json()

    def get_things(self, thing_ids: list[str]) -> list[dict[str, Any]]:
        if not thing_ids:
            return []
        resp = self._request("GET", "/things", params={"ids": ",".join(thing_ids)})
        return [] if resp.status_code == 404 else resp.json()

    def merge_thing(self, thing_id: str, patch: dict[str, Any]) -> None:
        self._request(
            "PATCH",
            f"/things/{thing_id}",
            content=json.dumps(patch),
            headers={"content-type": MERGE_PATCH},
        )

    def set_policy_id(self, thing_id: str, policy_id: str) -> None:
        self._request("PUT", f"/things/{thing_id}/policyId", json=policy_id)
