"""Pydantic schemas for VoiceNav (M9)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.common.schemas import ORMModel

Channel = Literal["voice", "chat"]
Lang = Literal["en", "hi"]
Tier = Literal["T0", "T1", "T2", "T3"]
Router = Literal["rules", "llm", "none"]
ActionStatus = Literal["pending", "confirmed", "cancelled", "expired", "executed", "failed", "rejected"]


# ── Sessions ──────────────────────────────────────────────────────────


class SessionCreate(BaseModel):
    channel: Channel = "chat"
    device: str | None = Field(None, max_length=128)
    lang: Lang = "en"


class SessionOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    started_at: datetime
    ended_at: datetime | None
    channel: str
    device: str | None
    lang: str
    context: dict[str, Any]


class TurnOut(ORMModel):
    id: uuid.UUID
    session_id: uuid.UUID
    at: datetime
    transcript: str | None
    transcript_confidence: float | None
    intent: str | None
    slots: dict[str, Any] | None
    intent_confidence: float | None
    router: str | None
    router_ms: int | None
    tier: str | None
    response_text: str | None
    citations: dict[str, Any] | None
    total_ms: int | None


class SessionDetail(SessionOut):
    turns: list[TurnOut] = Field(default_factory=list)


# ── Actions ───────────────────────────────────────────────────────────


class ActionOut(ORMModel):
    id: uuid.UUID
    turn_id: uuid.UUID
    tool: str
    params: dict[str, Any]
    tier: str
    readback: str | None
    status: str
    validation_errors: dict[str, Any] | None
    expires_at: datetime | None
    confirmed_at: datetime | None
    second_factor_ok: bool | None
    executed_at: datetime | None
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime


class ActionConfirm(BaseModel):
    # The PIN is a T3 second factor; it is validated against Keycloak and never stored or audited.
    pin: str | None = Field(None, min_length=4, max_length=12, pattern=r"^\d+$")


# ── The turn a caller actually posts ──────────────────────────────────


class UtteranceIn(BaseModel):
    """One thing the operator said or typed. Identical for voice and chat (FR-NL-04)."""

    text: str = Field(min_length=1, max_length=500)
    session_id: uuid.UUID | None = None
    lang: Lang | None = None
    channel: Channel = "chat"
    # The speech service supplies these; a typed message has neither.
    transcript_confidence: float | None = Field(None, ge=0, le=1)
    stt_ms: int | None = Field(None, ge=0)
    snr_db: float | None = None


class Suggestion(BaseModel):
    label: str
    value: str


class TurnResponse(BaseModel):
    """Everything the client needs to render one exchange, whether spoken or typed."""

    session_id: uuid.UUID
    turn_id: uuid.UUID
    intent: str
    tier: Tier
    router: Router
    confidence: float
    lang: str
    slots: dict[str, Any] = Field(default_factory=dict)
    text: str
    citations: dict[str, Any] = Field(default_factory=dict)
    hypothetical: bool = False
    # Present only when the intent is T2/T3 and is waiting for the operator to agree.
    action: ActionOut | None = None
    # "Did you mean …?" alternatives when a reference or the transcript was ambiguous.
    suggestions: list[Suggestion] = Field(default_factory=list)
    navigate: dict[str, Any] | None = None
    total_ms: int = 0


class IntentHelp(BaseModel):
    intent: str
    tier: str
    summary: str
    examples: dict[str, str]


class SuiteAccuracy(BaseModel):
    split: str
    total: int
    correct: int
    accuracy: float
    # Slots are counted per labelled value, not per utterance, so an utterance pinning down an
    # asset and a task contributes two. `slot_accuracy` is null for a split that labels none.
    slots_total: int = 0
    slots_correct: int = 0
    slot_accuracy: float | None = None
