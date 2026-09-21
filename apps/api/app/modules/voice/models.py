"""ORM models for VoiceNav (M9): sessions, turns, actions and the labelled intent suite."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, PKMixin

CHANNELS = ("voice", "chat")
ROUTERS = ("rules", "llm", "none")
TIERS = ("T0", "T1", "T2", "T3")
ACTION_STATUSES = ("pending", "confirmed", "cancelled", "expired", "executed", "failed", "rejected")

# A read-back that is neither confirmed nor cancelled within the window is dead, not merely stale:
# an operator who walked away must not have an order created when they come back.
PENDING_STATUSES = ("pending", "confirmed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(v) for v in values)})"


class VoiceSession(PKMixin, Base):
    __tablename__ = "voice_sessions"
    __table_args__ = (
        CheckConstraint(_in("channel", CHANNELS), name="channel"),
        Index("ix_voice_sessions_user_id_started_at", "user_id", text("started_at desc")),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None]
    channel: Mapped[str]
    device: Mapped[str | None]
    lang: Mapped[str] = mapped_column(server_default="en")
    # {current_asset, current_asset_id, last_prediction_id, last_explanation_id, last_alarm_id, last_list}
    context: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))


class VoiceTurn(PKMixin, Base):
    __tablename__ = "voice_turns"
    __table_args__ = (
        CheckConstraint(f"router is null or {_in('router', ROUTERS)}", name="router"),
        CheckConstraint(f"tier is null or {_in('tier', TIERS)}", name="tier"),
        Index("ix_voice_turns_session_id_at", "session_id", "at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("voice_sessions.id"))
    at: Mapped[datetime] = mapped_column(server_default=func.now())
    transcript: Mapped[str | None] = mapped_column(Text)
    transcript_confidence: Mapped[float | None] = mapped_column(Float)
    stt_ms: Mapped[int | None]
    intent: Mapped[str | None]
    slots: Mapped[dict[str, Any] | None]
    intent_confidence: Mapped[float | None] = mapped_column(Float)
    router: Mapped[str | None]
    router_ms: Mapped[int | None]
    tier: Mapped[str | None]
    response_text: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[dict[str, Any] | None]
    tts_ms: Mapped[int | None]
    total_ms: Mapped[int | None]
    snr_db: Mapped[float | None] = mapped_column(Float)
    audio_uri: Mapped[str | None]


class VoiceAction(PKMixin, Base):
    __tablename__ = "voice_actions"
    __table_args__ = (
        CheckConstraint(_in("tier", TIERS), name="tier"),
        CheckConstraint(_in("status", ACTION_STATUSES), name="status"),
        Index("ix_voice_actions_status", "status"),
        Index("ix_voice_actions_turn_id", "turn_id"),
    )

    turn_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("voice_turns.id"))
    tool: Mapped[str]
    params: Mapped[dict[str, Any]]
    tier: Mapped[str]
    readback: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(server_default="pending")
    validation_errors: Mapped[dict[str, Any] | None]
    expires_at: Mapped[datetime | None]
    confirmed_at: Mapped[datetime | None]
    second_factor_ok: Mapped[bool | None] = mapped_column(Boolean)
    executed_at: Mapped[datetime | None]
    result: Mapped[dict[str, Any] | None]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class IntentExample(PKMixin, Base):
    __tablename__ = "intent_examples"
    __table_args__ = (Index("intent_examples_uq", "intent", "lang", "text", "split", unique=True),)

    intent: Mapped[str]
    lang: Mapped[str]
    text: Mapped[str] = mapped_column(Text)
    slots: Mapped[dict[str, Any] | None]
    noise_variant: Mapped[bool] = mapped_column(Boolean, server_default="false")
    split: Mapped[str] = mapped_column(server_default="test")
