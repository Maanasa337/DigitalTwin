"""API tests for VoiceNav (M9), against compose `postgres`.

The unit-level grammar, slot and tier behaviour is covered in `packages/nlu`. What is tested here is
what only the API can be wrong about: that a spoken reference reaches the right row, that a T2
intent cannot execute without a confirmation, and that everything that happened is on the record.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.models import AuditLog
from app.modules.telemetry.models import Alarm
from app.modules.voice.models import VoiceAction, VoiceSession, VoiceTurn
from tests.conftest import auth

V1 = "/api/v1"


def chat(client: TestClient, text: str, role: str = "engineer", **extra: Any) -> dict[str, Any]:
    response = client.post(f"{V1}/chat", json={"text": text, **extra}, headers=auth(role))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def alarm(session: Session, seeded_asset: dict[str, Any]) -> Alarm:
    row = Alarm(
        asset_id=uuid.UUID(seeded_asset["id"]),
        severity="critical",
        title="Spindle vibration high",
        message="4.9 mm/s exceeds the alarm threshold",
        status="active",
    )
    session.add(row)
    session.flush()
    return row


# ── Sessions and text parity (FR-NL-04) ───────────────────────────────


def test_a_chat_turn_opens_a_session_and_records_the_turn(client: TestClient, session: Session):
    body = chat(client, "what can you do")
    assert body["intent"] == "help"
    assert body["router"] == "rules"
    assert "report" in body["text"].lower()

    turns = session.scalars(select(VoiceTurn).where(VoiceTurn.session_id == uuid.UUID(body["session_id"]))).all()
    assert len(turns) == 1
    assert turns[0].transcript == "what can you do"
    assert turns[0].response_text == body["text"]
    assert turns[0].total_ms is not None


def test_voice_turns_and_chat_are_the_same_handler(client: TestClient):
    """FR-NL-04: the only difference a speech client makes is the metadata it can supply."""
    typed = chat(client, "how is cnc one")
    spoken = client.post(
        f"{V1}/voice/turns",
        json={"text": "how is cnc one", "channel": "voice", "stt_ms": 830, "snr_db": 68.0},
        headers=auth("engineer"),
    )
    assert spoken.status_code == 200, spoken.text
    assert spoken.json()["intent"] == typed["intent"] == "get_machine_status"
    assert spoken.json()["text"] == typed["text"]


def test_session_detail_lists_the_transcript(client: TestClient):
    first = chat(client, "help")
    chat(client, "what can you do", session_id=first["session_id"])
    detail = client.get(f"{V1}/voice/sessions/{first['session_id']}", headers=auth("engineer"))
    assert detail.status_code == 200
    assert len(detail.json()["turns"]) == 2


def test_intent_cheat_sheet_is_served(client: TestClient):
    response = client.get(f"{V1}/voice/intents", headers=auth("technician"))
    assert response.status_code == 200
    rows = response.json()
    assert {r["intent"] for r in rows} >= {"get_machine_status", "create_work_order", "help"}
    assert all(row["examples"].get("en") for row in rows)


# ── Asset resolution (FR-VN-04) ───────────────────────────────────────


def test_a_spoken_reference_reaches_the_right_asset(client: TestClient, seeded_asset: dict[str, Any]):
    body = chat(client, "how is cnc one")
    assert body["intent"] == "get_machine_status"
    assert body["slots"]["asset"] == "cnc 1"
    # No prediction has been written for this asset, so the answer says what is known and no more.
    assert "CNC Mill 01" in body["text"]
    assert "health estimate" in body["text"]
    assert "None" not in body["text"]


def test_an_unknown_machine_is_not_guessed_at(client: TestClient, seeded_asset: dict[str, Any]):
    body = chat(client, "how is hydraulic press nine")
    assert body["intent"] == "get_machine_status"
    assert "don't know" in body["text"].lower() or "did you mean" in body["text"].lower()


def test_a_low_confidence_transcript_asks_instead_of_acting(client: TestClient, seeded_asset: dict[str, Any]):
    """FR-VN-06: below 0.6 the assistant offers alternatives rather than picking one."""
    response = client.post(
        f"{V1}/voice/turns",
        json={"text": "how is cnc one", "channel": "voice", "transcript_confidence": 0.41},
        headers=auth("engineer"),
    )
    assert response.status_code == 200
    body = response.json()
    assert "did you mean" in body["text"].lower()
    assert body["suggestions"]


# ── Dialogue context (FR-VN-05) ───────────────────────────────────────


def test_context_carries_the_asset_into_the_next_turn(client: TestClient, session: Session, seeded_asset):
    first = chat(client, "how is cnc one")
    second = chat(client, "why", session_id=first["session_id"])
    assert second["intent"] == "explain_prediction"
    # Resolved from context, so it is not the "which machine do you mean?" branch.
    assert "which machine" not in second["text"].lower()

    row = session.get(VoiceSession, uuid.UUID(first["session_id"]))
    assert row.context["current_asset_code"] == "cnc-01"


def test_context_expires_after_two_minutes_of_silence(client: TestClient, session: Session, seeded_asset):
    first = chat(client, "how is cnc one")
    row = session.get(VoiceSession, uuid.UUID(first["session_id"]))
    row.context = {**row.context, "touched_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat()}
    session.flush()

    second = chat(client, "why", session_id=first["session_id"])
    assert "which machine" in second["text"].lower()


# ── Tiers (FR-VN-07) ──────────────────────────────────────────────────


def test_a_query_executes_without_confirmation(client: TestClient, seeded_asset: dict[str, Any]):
    body = chat(client, "any alarms on cnc one")
    assert body["tier"] == "T0"
    assert body["action"] is None


def test_a_what_if_is_marked_hypothetical(client: TestClient, seeded_asset: dict[str, Any]):
    body = chat(client, "how is cnc one")
    what_if = chat(client, "what if we reduce load to 80 percent", session_id=body["session_id"])
    assert what_if["tier"] == "T1"
    assert what_if["action"] is None


def test_a_work_order_is_read_back_before_it_is_created(
    client: TestClient, session: Session, seeded_asset: dict[str, Any]
):
    body = chat(client, "schedule bearing replacement for cnc one on friday morning")
    assert body["intent"] == "create_work_order"
    assert body["tier"] == "T2"
    action = body["action"]
    assert action is not None and action["status"] == "pending"
    assert "bearing replacement" in action["readback"]
    assert "CNC Mill 01" in action["readback"]
    assert action["readback"].endswith("Say confirm or cancel.")

    # Nothing has been written yet — that is the whole point of the read-back.
    from app.modules.maintenance.models import WorkOrder

    assert session.scalars(select(WorkOrder)).all() == []


def test_confirming_the_read_back_creates_the_work_order(
    client: TestClient, session: Session, seeded_asset: dict[str, Any]
):
    from app.modules.maintenance.models import WorkOrder

    body = chat(client, "schedule bearing replacement for cnc one on friday morning")
    confirm = client.post(f"{V1}/voice/actions/{body['action']['id']}/confirm", json={}, headers=auth("engineer"))
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "executed"

    orders = session.scalars(select(WorkOrder)).all()
    assert len(orders) == 1
    assert orders[0].created_via == "voice"
    assert orders[0].title == "bearing replacement"
    assert orders[0].planned_start is not None


def test_saying_confirm_executes_the_pending_read_back(
    client: TestClient, session: Session, seeded_asset: dict[str, Any]
):
    """The spoken path: "confirm" is a control word acting on the session's one pending action."""
    from app.modules.maintenance.models import WorkOrder

    body = chat(client, "schedule bearing replacement for cnc one on friday morning")
    spoken = chat(client, "confirm", session_id=body["session_id"])
    assert spoken["action"]["status"] == "executed"
    assert len(session.scalars(select(WorkOrder)).all()) == 1


def test_a_sentence_containing_confirm_does_not_execute(client: TestClient, seeded_asset: dict[str, Any]):
    """Only the exact control words execute (Appendix A) — this is the false-execution guard."""

    body = chat(client, "schedule bearing replacement for cnc one on friday morning")
    follow_up = chat(client, "confirm the order for compressor two later", session_id=body["session_id"])
    assert follow_up["intent"] != "create_work_order" or follow_up["action"]["status"] == "pending"

    action = client.get(f"{V1}/voice/sessions/{body['session_id']}", headers=auth("engineer"))
    assert action.status_code == 200


def test_cancelling_leaves_nothing_behind(client: TestClient, session: Session, seeded_asset: dict[str, Any]):
    from app.modules.maintenance.models import WorkOrder

    body = chat(client, "schedule bearing replacement for cnc one on friday morning")
    cancel = client.post(f"{V1}/voice/actions/{body['action']['id']}/cancel", json={}, headers=auth("engineer"))
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
    assert session.scalars(select(WorkOrder)).all() == []


def test_an_expired_read_back_cannot_be_confirmed(client: TestClient, session: Session, seeded_asset: dict[str, Any]):
    """Ten seconds is the window; after it the operator has to say it again."""
    body = chat(client, "schedule bearing replacement for cnc one on friday morning")
    action = session.get(VoiceAction, uuid.UUID(body["action"]["id"]))
    action.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.flush()

    confirm = client.post(f"{V1}/voice/actions/{action.id}/confirm", json={}, headers=auth("engineer"))
    assert confirm.status_code == 409
    assert session.get(VoiceAction, action.id).status == "expired"


def test_confirming_twice_is_rejected(client: TestClient, seeded_asset: dict[str, Any]):
    body = chat(client, "schedule bearing replacement for cnc one on friday morning")
    url = f"{V1}/voice/actions/{body['action']['id']}/confirm"
    assert client.post(url, json={}, headers=auth("engineer")).status_code == 200
    assert client.post(url, json={}, headers=auth("engineer")).status_code == 409


def test_parameters_are_revalidated_at_confirmation_time(
    client: TestClient, session: Session, seeded_asset: dict[str, Any], alarm: Alarm
):
    """The alarm was open at read-back and closed before the operator said confirm."""
    body = chat(client, "acknowledge the alarm on cnc one")
    assert body["tier"] == "T2"

    alarm.status = "cleared"
    session.flush()

    confirm = client.post(f"{V1}/voice/actions/{body['action']['id']}/confirm", json={}, headers=auth("engineer"))
    assert confirm.status_code == 200
    action = confirm.json()
    assert action["status"] == "rejected"
    assert "alarm" in action["validation_errors"]


def test_acknowledging_an_open_alarm_works(
    client: TestClient, session: Session, seeded_asset: dict[str, Any], alarm: Alarm
):
    body = chat(client, "acknowledge the alarm on cnc one")
    confirm = client.post(f"{V1}/voice/actions/{body['action']['id']}/confirm", json={}, headers=auth("engineer"))
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "executed"
    session.refresh(alarm)
    assert alarm.status == "acknowledged"


# ── T3 (FR-VN-07) ─────────────────────────────────────────────────────


def test_t3_needs_a_second_factor(client: TestClient, seeded_asset: dict[str, Any], simulator):
    simulator.routes[("POST", "/faults")] = lambda _: httpx.Response(200, json={"ok": True})
    body = chat(client, "inject a bearing fault on cnc one")
    assert body["tier"] == "T3"
    assert body["action"] is not None

    without_pin = client.post(f"{V1}/voice/actions/{body['action']['id']}/confirm", json={}, headers=auth("engineer"))
    assert without_pin.status_code == 403

    body = chat(client, "inject a bearing fault on cnc one")
    with_pin = client.post(
        f"{V1}/voice/actions/{body['action']['id']}/confirm",
        json={"pin": "246810"},
        headers=auth("engineer"),
    )
    assert with_pin.status_code == 200, with_pin.text
    assert with_pin.json()["status"] == "executed"
    assert with_pin.json()["second_factor_ok"] is True


def test_t3_is_refused_outright_when_actuation_is_disabled(
    client: TestClient, settings: Settings, seeded_asset: dict[str, Any]
):
    settings.allow_t3 = False
    body = chat(client, "inject a bearing fault on cnc one")
    assert body["action"] is None
    assert "disabled" in body["text"].lower()


# ── Audit (FR-VN-07: every step logged) ───────────────────────────────


def test_every_step_of_a_confirmed_action_is_audited(
    client: TestClient, session: Session, seeded_asset: dict[str, Any]
):
    body = chat(client, "schedule bearing replacement for cnc one on friday morning")
    client.post(f"{V1}/voice/actions/{body['action']['id']}/confirm", json={}, headers=auth("engineer"))

    actions = session.scalars(
        select(AuditLog).where(
            AuditLog.entity == "voice_actions", AuditLog.entity_id == uuid.UUID(body["action"]["id"])
        )
    ).all()
    assert {row.action for row in actions} == {"read_back", "executed"}
    assert all(row.actor_id is not None for row in actions)


def test_a_rejected_action_records_why(client: TestClient, session: Session, seeded_asset, alarm: Alarm):
    body = chat(client, "acknowledge the alarm on cnc one")
    alarm.status = "cleared"
    session.flush()
    client.post(f"{V1}/voice/actions/{body['action']['id']}/confirm", json={}, headers=auth("engineer"))

    rejected = session.scalars(
        select(AuditLog).where(AuditLog.entity == "voice_actions", AuditLog.action == "rejected")
    ).all()
    assert len(rejected) == 1
    assert "alarm" in rejected[0].after


# ── Navigation (FR-NL-05) ─────────────────────────────────────────────


def test_navigation_returns_a_route_for_the_front_end(client: TestClient, seeded_asset: dict[str, Any]):
    body = chat(client, "show energy")
    assert body["intent"] == "navigate_dashboard"
    assert body["navigate"]["path"] == "/analytics/energy"

    to_asset = chat(client, "open cnc one")
    assert to_asset["navigate"]["path"] == "/machines/cnc-01"


def test_a_named_view_outranks_the_asset_in_context(client: TestClient, seeded_asset: dict[str, Any]):
    """ "Show energy" after asking about a machine opens the energy page, not the machine page."""
    first = chat(client, "how is cnc one")
    body = chat(client, "show energy", session_id=first["session_id"])
    assert body["navigate"]["path"] == "/analytics/energy"
    # The asset stays available to the page as context, it just does not decide the route.
    assert body["navigate"]["asset_code"] == "cnc-01"


def test_a_view_with_an_explicit_asset_still_opens_the_view(client: TestClient, seeded_asset: dict[str, Any]):
    body = chat(client, "show energy for cnc one")
    assert body["navigate"]["path"] == "/analytics/energy"
    assert body["navigate"]["asset_code"] == "cnc-01"


# ── The intent suite (FR-NL-06) ───────────────────────────────────────


def test_seeding_the_suite_is_idempotent_and_accuracy_is_measured(client: TestClient):
    first = client.post(f"{V1}/voice/suite", headers=auth("engineer"))
    assert first.status_code == 201, first.text
    seeded = first.json()["seeded"]
    assert seeded >= 500

    again = client.post(f"{V1}/voice/suite", headers=auth("engineer"))
    assert again.status_code == 201
    assert again.json()["seeded"] == seeded

    accuracy = client.get(f"{V1}/voice/suite-accuracy", headers=auth("engineer"))
    assert accuracy.status_code == 200
    splits = {row["split"]: row for row in accuracy.json()}
    assert splits["test"]["accuracy"] >= 0.92, splits["test"]
    for split, row in splits.items():
        assert row["accuracy"] >= 0.85, (split, row)


def test_seeding_the_suite_requires_an_engineer(client: TestClient):
    assert client.post(f"{V1}/voice/suite", headers=auth("technician")).status_code == 403
    assert client.get(f"{V1}/voice/suite-accuracy", headers=auth("technician")).status_code == 403


def test_a_turn_requires_authentication(client: TestClient):
    assert client.post(f"{V1}/chat", json={"text": "help"}).status_code == 401
