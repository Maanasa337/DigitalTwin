from typing import Any

import httpx

from app.core.errors import BadGatewayError, NotFoundError, ServiceUnavailableError, UnprocessableError


class SimulatorClient:
    """Proxy to the simulator's internal control API (apps/simulator, not reachable from browsers)."""

    def __init__(self, base_url: str, timeout: float = 10.0, transport: httpx.BaseTransport | None = None) -> None:
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def request(self, method: str, path: str, json: Any = None, timeout: float | None = None) -> Any:
        try:
            resp = self._http.request(
                method, path, json=json, timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT
            )
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError("Simulator unreachable") from exc
        if resp.status_code == 404:
            raise NotFoundError(_detail(resp))
        if resp.status_code == 422:
            raise UnprocessableError(_detail(resp))
        if resp.status_code >= 400:
            raise BadGatewayError(f"Simulator error {resp.status_code}: {_detail(resp)}")
        return resp.json()


def _detail(resp: httpx.Response) -> str:
    try:
        detail = resp.json().get("detail", resp.text)
    except ValueError:
        return resp.text
    return detail if isinstance(detail, str) else str(detail)
