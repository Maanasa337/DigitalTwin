"""Every list endpoint answers with a page.

Three routers build `PageParams` themselves rather than through the `page_params` dependency, and
each of them omitted `sort`, so `GET /alarms`, `GET /alarm-rules` and `GET /models` raised a
TypeError on every call. This sweeps the list endpoints so a fourth one cannot do it quietly.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.common.pagination import PageParams
from tests.conftest import auth

V1 = "/api/v1"

LIST_ENDPOINTS = [
    "/assets",
    "/lines",
    "/plants",
    "/alarms",
    "/alarm-rules",
    "/models",
    "/technicians",
    "/work-orders",
    "/reports",
    "/report-schedules",
    "/shifts",
    "/tariffs",
]


def test_sort_is_optional():
    """The routers that construct it directly rely on this default."""
    assert PageParams(page=1, size=20).sort is None


@pytest.mark.parametrize("path", LIST_ENDPOINTS)
def test_list_endpoint_returns_a_page(client: TestClient, path: str):
    response = client.get(f"{V1}{path}", headers=auth("engineer"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) >= {"items", "total", "page", "size"}
    assert isinstance(body["items"], list)


@pytest.mark.parametrize("path", ["/assets", "/work-orders", "/reports"])
def test_list_endpoint_accepts_a_sort(client: TestClient, path: str):
    response = client.get(f"{V1}{path}", params={"sort": "-created_at"}, headers=auth("engineer"))
    assert response.status_code == 200, response.text


def test_an_unsortable_field_is_rejected_rather_than_ignored(client: TestClient):
    response = client.get(f"{V1}/assets", params={"sort": "nonsense"}, headers=auth("engineer"))
    assert response.status_code == 422
