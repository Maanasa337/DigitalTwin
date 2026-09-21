"""Tests for reporting (M10): the numeric audit, the renderers, and the API against compose `postgres`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.reports import render, summary
from app.modules.reports.models import Report
from app.modules.reports.service import ReportService
from app.workers.tasks.report import _is_due
from tests.conftest import auth

V1 = "/api/v1"

FIGURES = {
    "scope_name": "Line 1",
    "raised": 7,
    "closed": 5,
    "mtbf_h": 42.5,
    "mttr_h": 3.2,
    "breakdowns": 2,
    "predictions_scored": 4,
    "predictions_correct": 3,
    "prediction_accuracy_pct": 75.0,
    "by_status": {"open": 2, "closed": 5},
    "orders": [{"number": 11, "asset": "CNC Mill 01", "title": "Bearing", "status": "closed"}],
}


# ── The numeric audit (FR-RP-04) ──────────────────────────────────────


def test_supported_numbers_are_found_at_any_depth():
    found = summary.supported_numbers({"a": 1.5, "b": [{"c": 2.25}], "d": "seen 3 times"})
    assert {1.5, 2.25, 3.0} <= found


def test_a_summary_that_invents_a_number_fails_the_audit():
    result = summary.audit("MTBF was 99.9 hours across 2 breakdowns.", FIGURES, used_llm=True)
    assert not result.passed
    assert 99.9 in result.unsupported_numbers
    assert result.reason == "numbers not present in the report data"


def test_a_summary_built_from_the_figures_passes():
    text = "7 orders were raised and 5 closed, with MTBF 42.5 hours and 2 breakdowns."
    assert summary.audit(text, FIGURES, used_llm=True).passed


def test_rounding_within_tolerance_is_accepted():
    """A summary may say 42.5; it may not say 45."""
    assert summary.audit("MTBF was 42.5 hours.", FIGURES, used_llm=True).passed
    assert not summary.audit("MTBF was 45 hours.", FIGURES, used_llm=True).passed


def test_an_overlong_summary_fails_the_audit():
    long_text = " ".join(["7"] * (summary.WORD_LIMIT + 5))
    result = summary.audit(long_text, FIGURES, used_llm=True)
    assert not result.passed
    assert "limit" in result.reason


def test_without_an_llm_the_template_summary_is_used():
    text, audit = summary.compose("weekly_maintenance", FIGURES, endpoint=None)
    assert not audit.used_llm
    assert audit.passed
    assert "7 work orders were raised" in text
    assert "42.5" in text


def test_the_template_summary_never_claims_an_accuracy_it_does_not_have():
    """None is not zero: an unscored week must not be reported as 0 % accurate."""
    figures = {**FIGURES, "prediction_accuracy_pct": None, "predictions_scored": 0}
    text, _ = summary.compose("weekly_maintenance", figures, endpoint=None)
    assert "0 percent" not in text
    assert "No closed order was scored" in text


@pytest.mark.parametrize(
    "report_type",
    ["machine_health", "weekly_maintenance", "energy", "benchmark", "incident"],
)
def test_every_report_type_has_a_template_summary(report_type: str):
    assert summary.template_summary(report_type, FIGURES)


# ── Rendering (FR-RP-02) ──────────────────────────────────────────────


def context(report_type: str = "weekly_maintenance", data: dict[str, Any] | None = None) -> dict[str, Any]:
    figures = data if data is not None else FIGURES
    text, audit = summary.compose(report_type, figures, endpoint=None)
    return render.build_context(
        report_id=str(uuid.uuid4()),
        report_type=report_type,
        scope_name="Line 1",
        period_start=datetime(2026, 9, 14, tzinfo=UTC),
        period_end=datetime(2026, 9, 21, tzinfo=UTC),
        generated_at=datetime(2026, 9, 21, 9, 0, tzinfo=UTC),
        data=figures,
        charts={},
        summary_text=text,
        summary_audit=audit.to_dict(),
        llm_model="qwen3",
    )


def test_html_renders_the_figures_and_the_summary():
    html = render.render_html(context())
    assert "Weekly maintenance report" in html
    assert "42.5" in html
    assert "Line 1" in html
    assert "counter(page)" in html  # the print stylesheet, so the PDF is paginated


@pytest.mark.parametrize(
    "report_type",
    ["machine_health", "weekly_maintenance", "energy", "benchmark", "incident"],
)
def test_every_template_renders_from_empty_data(report_type: str):
    """A report for a period with nothing in it still renders, saying so rather than failing."""
    from app.modules.reports.service import ReportService  # noqa: F401  (import kept local)

    empty = _empty_figures(report_type)
    html = render.render_html(context(report_type, empty))
    assert render.TITLES[report_type] in html


def _empty_figures(report_type: str) -> dict[str, Any]:
    common = {"scope_name": "Line 1"}
    match report_type:
        case "machine_health":
            return {
                **common,
                "asset": {"code": "cnc-01", "name": "CNC Mill 01", "type": "cnc_mill", "status": "RUNNING"},
                "health_pct": None,
                "rul": None,
                "rul_low": None,
                "rul_high": None,
                "rul_unit": "cycles",
                "confidence": None,
                "oee_pct": None,
                "availability_pct": None,
                "performance_pct": None,
                "quality_pct": None,
                "alarm_count": 0,
                "open_work_orders": 0,
                "health_series": [],
                "rul_series": [],
                "alarms": [],
                "work_orders": [],
            }
        case "weekly_maintenance":
            return {
                **common,
                "raised": 0,
                "closed": 0,
                "by_status": {},
                "by_type": {},
                "predictions_scored": 0,
                "predictions_correct": 0,
                "prediction_accuracy_pct": None,
                "mtbf_h": None,
                "mttr_h": None,
                "breakdowns": 0,
                "orders": [],
            }
        case "energy":
            return {
                **common,
                "energy_kwh": None,
                "cost": None,
                "currency": "INR",
                "co2_kg": None,
                "peak_demand_kw": None,
                "idle_energy_kwh": None,
                "idle_energy_share_pct": None,
                "energy_per_unit": None,
                "top_consumers": [],
                "intensity_trend": [],
                "anomaly_count": 0,
                "anomalies": [],
            }
        case "benchmark":
            return {**common, "run": None, "production_models": [], "model_count": 0}
        case _:
            return {
                **common,
                "asset": {"code": "cnc-01", "name": "CNC Mill 01"},
                "failure_at": "2026-09-20T10:00:00+00:00",
                "window_hours": 48,
                "prediction_count": 0,
                "alarm_count": 0,
                "work_order_count": 0,
                "recommended_actions": [],
                "actions_taken": [],
                "timeline": [],
            }


def test_markdown_carries_the_same_figures():
    text = render.render_markdown(context())
    assert text.startswith("# Weekly maintenance report")
    assert "42.5" in text


def test_docx_produces_a_real_word_file():
    content, produced = render.render(context(), "docx")
    assert produced == "docx"
    assert content[:2] == b"PK"  # a .docx is a zip container


def test_pdf_falls_back_to_html_without_the_native_libraries():
    """On a host with pango/cairo this is a PDF; without them the HTML is delivered and said to be."""
    content, produced = render.render(context(), "pdf")
    if render.weasyprint_available():
        assert produced == "pdf"
        assert content[:5] == b"%PDF-"
    else:
        assert produced == "html"
        assert b"<!doctype html>" in content[:64].lower()


# ── Schedule cron matching (FR-RP-03) ─────────────────────────────────

MONDAY_6AM = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)


def test_a_cron_fires_only_on_a_matching_minute():
    assert _is_due("0 6 * * 1", MONDAY_6AM, None)
    assert not _is_due("0 6 * * 1", MONDAY_6AM + timedelta(minutes=1), None)
    assert not _is_due("0 6 * * 2", MONDAY_6AM, None)


def test_a_schedule_that_just_ran_does_not_fire_again():
    """Beat ticks every minute; without this a 06:00 schedule would fire on every tick of that minute."""
    assert not _is_due("0 6 * * 1", MONDAY_6AM, MONDAY_6AM - timedelta(seconds=30))
    assert _is_due("0 6 * * 1", MONDAY_6AM, MONDAY_6AM - timedelta(days=7))


# ── API ───────────────────────────────────────────────────────────────


@pytest.fixture
def archive(tmp_path: Path, session: Session) -> ReportService:
    """A service writing into a temporary archive, so tests never touch data/reports."""
    from app.core.config import Settings

    return ReportService(session, settings=Settings(), archive_root=tmp_path)


def test_requesting_a_report_queues_it(client: TestClient, session: Session, plant_line: dict[str, Any]):
    response = client.post(
        f"{V1}/reports",
        json={"type": "weekly_maintenance", "scope": "line", "scope_id": plant_line["line"]["id"], "format": "md"},
        headers=auth("engineer"),
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["requested_via"] == "ui"
    # The period defaults to the last week rather than being left open.
    assert body["period_start"] and body["period_end"]


def test_a_machine_health_report_needs_an_asset(client: TestClient, plant_line: dict[str, Any]):
    response = client.post(f"{V1}/reports", json={"type": "machine_health", "scope": "asset"}, headers=auth("engineer"))
    assert response.status_code == 422


def test_generating_produces_a_file_and_an_audited_summary(
    client: TestClient, session: Session, archive: ReportService, plant_line: dict[str, Any]
):
    from app.modules.reports.schemas import ReportCreate
    from tests.conftest import USERS

    report = archive.request(
        USERS["engineer"],
        ReportCreate(
            type="weekly_maintenance", scope="line", scope_id=uuid.UUID(plant_line["line"]["id"]), format="md"
        ),
    )
    generated = archive.generate(report.id)

    assert generated.status == "done", generated.error
    assert generated.summary_text
    assert generated.summary_audit["passed"] is True
    assert generated.data is not None
    assert Path(generated.file_uri).exists()
    assert Path(generated.file_uri).read_text(encoding="utf-8").startswith("# Weekly maintenance report")


def test_the_archive_path_is_derived_from_the_report_id(
    session: Session, archive: ReportService, plant_line: dict[str, Any]
):
    from app.modules.reports.schemas import ReportCreate
    from tests.conftest import USERS

    report = archive.request(
        USERS["engineer"],
        ReportCreate(
            type="weekly_maintenance", scope="line", scope_id=uuid.UUID(plant_line["line"]["id"]), format="md"
        ),
    )
    generated = archive.generate(report.id)
    path = Path(generated.file_uri)
    assert path.stem == str(report.id)
    assert path.parent.name == f"{report.created_at:%m}"
    assert path.parent.parent.name == f"{report.created_at:%Y}"


def test_the_file_endpoint_serves_a_finished_report(
    client: TestClient, session: Session, archive: ReportService, plant_line: dict[str, Any]
):
    from app.modules.reports.schemas import ReportCreate
    from tests.conftest import USERS

    report = archive.request(
        USERS["engineer"],
        ReportCreate(
            type="weekly_maintenance", scope="line", scope_id=uuid.UUID(plant_line["line"]["id"]), format="md"
        ),
    )
    archive.generate(report.id)

    response = client.get(f"{V1}/reports/{report.id}/file", headers=auth("engineer"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert b"Weekly maintenance report" in response.content


def test_a_queued_report_has_no_file_yet(client: TestClient, plant_line: dict[str, Any]):
    created = client.post(
        f"{V1}/reports",
        json={"type": "energy", "scope": "line", "scope_id": plant_line["line"]["id"]},
        headers=auth("engineer"),
    ).json()
    response = client.get(f"{V1}/reports/{created['id']}/file", headers=auth("engineer"))
    assert response.status_code == 409


def test_a_failed_report_records_the_error_rather_than_raising(
    session: Session, archive: ReportService, plant_line: dict[str, Any]
):
    report = Report(
        type="machine_health",
        scope="asset",
        scope_id=uuid.uuid4(),  # no such asset
        period_start=datetime.now(UTC) - timedelta(days=1),
        period_end=datetime.now(UTC),
        format="md",
        status="queued",
    )
    session.add(report)
    session.flush()

    generated = archive.generate(report.id)
    assert generated.status == "failed"
    assert generated.error
    assert generated.finished_at is not None


# ── Access control (FR-RP-06) ─────────────────────────────────────────


def test_a_technician_does_not_see_energy_or_benchmark_reports(
    client: TestClient, session: Session, plant_line: dict[str, Any]
):
    for report_type in ("weekly_maintenance", "energy", "benchmark"):
        client.post(
            f"{V1}/reports",
            json={"type": report_type, "scope": "line", "scope_id": plant_line["line"]["id"]},
            headers=auth("engineer"),
        )

    engineer = client.get(f"{V1}/reports", headers=auth("engineer")).json()
    technician = client.get(f"{V1}/reports", headers=auth("technician")).json()
    assert {r["type"] for r in engineer["items"]} == {"weekly_maintenance", "energy", "benchmark"}
    assert {r["type"] for r in technician["items"]} == {"weekly_maintenance"}


def test_a_technician_cannot_download_a_report_type_they_cannot_list(
    client: TestClient, session: Session, archive: ReportService, plant_line: dict[str, Any]
):
    from app.modules.reports.schemas import ReportCreate
    from tests.conftest import USERS

    report = archive.request(
        USERS["engineer"],
        ReportCreate(type="benchmark", scope="line", scope_id=uuid.UUID(plant_line["line"]["id"]), format="md"),
    )
    archive.generate(report.id)
    assert client.get(f"{V1}/reports/{report.id}/file", headers=auth("technician")).status_code == 403


# ── Schedules ─────────────────────────────────────────────────────────


def test_schedule_crud(client: TestClient, plant_line: dict[str, Any]):
    created = client.post(
        f"{V1}/report-schedules",
        json={
            "type": "weekly_maintenance",
            "scope": "line",
            "scope_id": plant_line["line"]["id"],
            "format": "pdf",
            "cron": "0 6 * * 1",
            "recipients": ["plant@example.test"],
        },
        headers=auth("engineer"),
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]

    listed = client.get(f"{V1}/report-schedules", headers=auth("technician"))
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    patched = client.patch(f"{V1}/report-schedules/{schedule_id}", json={"enabled": False}, headers=auth("engineer"))
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    assert client.delete(f"{V1}/report-schedules/{schedule_id}", headers=auth("engineer")).status_code == 204
    assert client.get(f"{V1}/report-schedules", headers=auth("engineer")).json()["total"] == 0


def test_an_invalid_cron_is_rejected(client: TestClient):
    response = client.post(
        f"{V1}/report-schedules",
        json={"type": "energy", "format": "pdf", "cron": "every monday"},
        headers=auth("engineer"),
    )
    assert response.status_code == 422


def test_creating_a_schedule_requires_a_write_role(client: TestClient):
    response = client.post(
        f"{V1}/report-schedules",
        json={"type": "energy", "format": "pdf", "cron": "0 6 * * 1"},
        headers=auth("technician"),
    )
    assert response.status_code == 403


# ── The voice path into reports (FR-RP-03, FR-RP-05) ──────────────────


def test_generating_a_report_by_voice_is_read_back_first(
    client: TestClient, session: Session, seeded_asset: dict[str, Any]
):
    body = client.post(
        f"{V1}/chat", json={"text": "generate the weekly maintenance report"}, headers=auth("engineer")
    ).json()
    assert body["intent"] == "generate_report"
    assert body["tier"] == "T2"
    assert "weekly maintenance" in body["action"]["readback"]
    assert session.scalars(select(Report)).all() == []

    confirm = client.post(f"{V1}/voice/actions/{body['action']['id']}/confirm", json={}, headers=auth("engineer"))
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "executed"

    reports = session.scalars(select(Report)).all()
    assert len(reports) == 1
    assert reports[0].requested_via == "voice"
    assert reports[0].type == "weekly_maintenance"
