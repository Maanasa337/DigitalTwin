"""Repository layer for VoiceNav (M9)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.assets.models import Asset, Line
from app.modules.voice.models import IntentExample, VoiceAction, VoiceSession, VoiceTurn


class SessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, session_id: uuid.UUID) -> VoiceSession | None:
        return self.session.get(VoiceSession, session_id)

    def create(self, row: VoiceSession) -> VoiceSession:
        self.session.add(row)
        self.session.flush()
        return row

    def for_user(self, user_id: uuid.UUID | None, limit: int) -> list[VoiceSession]:
        stmt = select(VoiceSession).order_by(VoiceSession.started_at.desc()).limit(limit)
        if user_id is not None:
            stmt = stmt.where(VoiceSession.user_id == user_id)
        return list(self.session.scalars(stmt))

    def turns(self, session_id: uuid.UUID) -> list[VoiceTurn]:
        return list(
            self.session.scalars(select(VoiceTurn).where(VoiceTurn.session_id == session_id).order_by(VoiceTurn.at))
        )

    def last_turn(self, session_id: uuid.UUID) -> VoiceTurn | None:
        return self.session.scalars(
            select(VoiceTurn).where(VoiceTurn.session_id == session_id).order_by(VoiceTurn.at.desc())
        ).first()

    def add_turn(self, turn: VoiceTurn) -> VoiceTurn:
        self.session.add(turn)
        self.session.flush()
        return turn


class ActionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, action_id: uuid.UUID) -> VoiceAction | None:
        return self.session.get(VoiceAction, action_id)

    def create(self, action: VoiceAction) -> VoiceAction:
        self.session.add(action)
        self.session.flush()
        return action

    def pending_for_session(self, session_id: uuid.UUID, now: datetime) -> VoiceAction | None:
        """The one read-back a bare "confirm" refers to: newest, still pending, not yet expired."""
        return self.session.scalars(
            select(VoiceAction)
            .join(VoiceTurn, VoiceTurn.id == VoiceAction.turn_id)
            .where(
                VoiceTurn.session_id == session_id,
                VoiceAction.status == "pending",
                VoiceAction.expires_at > now,
            )
            .order_by(VoiceAction.created_at.desc())
        ).first()

    def expire_stale(self, now: datetime) -> int:
        """Mark every read-back whose window has closed. Idempotent, so the caller may run it often."""
        stale = list(
            self.session.scalars(
                select(VoiceAction).where(VoiceAction.status == "pending", VoiceAction.expires_at <= now)
            )
        )
        for action in stale:
            action.status = "expired"
        self.session.flush()
        return len(stale)


class AssetDirectory:
    """The asset names the fuzzy matcher scores against, including lines (a scope can be a line)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def assets(self) -> list[tuple[uuid.UUID, str, str]]:
        return [
            (row.id, row.code, row.name)
            for row in self.session.scalars(select(Asset).where(Asset.deleted_at.is_(None), Asset.status != "retired"))
        ]

    def lines(self) -> list[tuple[uuid.UUID, str, str]]:
        return [
            (row.id, row.code, row.name) for row in self.session.scalars(select(Line).where(Line.deleted_at.is_(None)))
        ]


class IntentExampleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(IntentExample)) or 0

    def all(self, split: str | None = None) -> list[IntentExample]:
        stmt = select(IntentExample)
        if split:
            stmt = stmt.where(IntentExample.split == split)
        return list(self.session.scalars(stmt))

    def replace_all(self, rows: list[IntentExample]) -> int:
        """The suite is derived from intents.yaml, so a reseed replaces rather than merges."""
        self.session.query(IntentExample).delete()
        self.session.add_all(rows)
        self.session.flush()
        return len(rows)
