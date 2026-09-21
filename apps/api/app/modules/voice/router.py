"""REST endpoints for VoiceNav (M9).

`/chat` and `/voice/turns` are the same handler: text parity is a routing fact, not a second
implementation (FR-NL-04). The speech service, when it arrives, posts transcripts to `/voice/turns`
with `stt_ms` and `snr_db` filled in; the browser's chat box posts to `/chat` without them.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import CurrentUser, SecondFactor, get_current_user, get_second_factor, require_role
from app.dependencies import get_simulator
from app.modules.voice.schemas import (
    ActionConfirm,
    ActionOut,
    IntentHelp,
    SessionCreate,
    SessionDetail,
    SessionOut,
    SuiteAccuracy,
    TurnResponse,
    UtteranceIn,
)
from app.modules.voice.service import VoiceService

router = APIRouter(tags=["voice"])
reader = Depends(get_current_user)


def get_voice_service(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    simulator: Any = Depends(get_simulator),
    second_factor: SecondFactor = Depends(get_second_factor),
) -> VoiceService:
    return VoiceService(session, settings=settings, simulator=simulator, second_factor=second_factor)


# ── Sessions ──────────────────────────────────────────────────────────


@router.post("/voice/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def start_session(
    data: SessionCreate,
    user: CurrentUser = Depends(get_current_user),
    service: VoiceService = Depends(get_voice_service),
) -> Any:
    return service.start_session(user, data.channel, data.device, data.lang)


@router.get("/voice/sessions", response_model=list[SessionOut])
def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    service: VoiceService = Depends(get_voice_service),
) -> Any:
    return service.recent_sessions(user, limit)


@router.get("/voice/sessions/{session_id}", response_model=SessionDetail, dependencies=[reader])
def get_session_detail(session_id: uuid.UUID, service: VoiceService = Depends(get_voice_service)) -> Any:
    return service.session_detail(session_id)


@router.post("/voice/sessions/{session_id}/end", response_model=SessionOut)
def end_session(
    session_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    service: VoiceService = Depends(get_voice_service),
) -> Any:
    return service.end_session(user, session_id)


# ── Turns ─────────────────────────────────────────────────────────────


@router.post("/voice/turns", response_model=TurnResponse)
def submit_turn(
    data: UtteranceIn,
    user: CurrentUser = Depends(get_current_user),
    service: VoiceService = Depends(get_voice_service),
) -> Any:
    return service.handle(user, data)


@router.post("/chat", response_model=TurnResponse)
def chat(
    data: UtteranceIn,
    user: CurrentUser = Depends(get_current_user),
    service: VoiceService = Depends(get_voice_service),
) -> Any:
    """Typed parity for every voice command: same router, same tiers, same logs (FR-NL-04)."""
    return service.handle(user, data.model_copy(update={"channel": "chat"}))


# ── Actions ───────────────────────────────────────────────────────────


@router.post("/voice/actions/{action_id}/confirm", response_model=ActionOut)
def confirm_action(
    action_id: uuid.UUID,
    data: ActionConfirm,
    user: CurrentUser = Depends(get_current_user),
    service: VoiceService = Depends(get_voice_service),
) -> Any:
    return service.confirm(user, action_id, data.pin)["action"]


@router.post("/voice/actions/{action_id}/cancel", response_model=ActionOut)
def cancel_action(
    action_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    service: VoiceService = Depends(get_voice_service),
) -> Any:
    return service.cancel(user, action_id)["action"]


# ── Help and the intent suite ─────────────────────────────────────────


@router.get("/voice/intents", response_model=list[IntentHelp], dependencies=[reader])
def list_intents(service: VoiceService = Depends(get_voice_service)) -> Any:
    return service.intents()


@router.get(
    "/voice/suite-accuracy",
    response_model=list[SuiteAccuracy],
    dependencies=[Depends(require_role("engineer", "admin"))],
)
def suite_accuracy(service: VoiceService = Depends(get_voice_service)) -> Any:
    """FR-NL-06 measured against the stored suite; empty until the examples have been seeded."""
    return service.suite_accuracy()


@router.post(
    "/voice/suite",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("engineer", "admin"))],
)
def seed_suite(service: VoiceService = Depends(get_voice_service)) -> dict[str, int]:
    return {"seeded": service.seed_intent_examples()}
