"""Service layer for VoiceNav (M9): dialogue state, slot resolution and the tier state machine.

One utterance travels: route it (`twinvoice_nlu`) → resolve its slots against the twin registry →
decide by tier whether it executes now or is read back → speak only what a tool returned.

The rules that matter, and where they live here:
  * Dialogue context (FR-VN-05) is on the session row, refreshed by every turn that names an asset,
    and treated as expired after `CONTEXT_TTL`. "Why?" two minutes later is a new question, not a
    follow-up about whatever the operator asked about before lunch.
  * A T2/T3 action (FR-VN-07) is a row, not in-process state: the read-back must survive a reload,
    a second browser tab and an API restart, and it must expire on its own.
  * Parameters are re-validated at confirmation time, not at read-back time, because the ten seconds
    in between are exactly when a technician's shift can end.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import valkey
from sqlalchemy.orm import Session
from twinvoice_nlu import fuzzy, narrate, tiers
from twinvoice_nlu.router import RouterResult, route
from twinvoice_nlu.rules import describe
from twinvoice_nlu.schema import load_catalogue
from twinvoice_nlu.suite import Utterance, score_slots

from app.core.audit import ensure_user, write_audit
from app.core.config import Settings, get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ProblemError, UnprocessableError
from app.core.security import CurrentUser
from app.modules.maintenance.models import Technician, TechnicianAvailability
from app.modules.voice import tools
from app.modules.voice.models import IntentExample, VoiceAction, VoiceSession, VoiceTurn
from app.modules.voice.repository import (
    ActionRepository,
    AssetDirectory,
    IntentExampleRepository,
    SessionRepository,
)
from app.modules.voice.schemas import TurnResponse, UtteranceIn

log = logging.getLogger(__name__)

CONTEXT_TTL = timedelta(minutes=2)  # FR-VN-05
# Parameters that are datetimes. `voice_actions.params` is JSONB, so they come back from a pending
# read-back as ISO strings and have to be revived before the tool sees them.
DATETIME_PARAMS = frozenset({"when", "planned_start", "planned_end", "period_start", "period_end"})
LOW_TRANSCRIPT_CONFIDENCE = 0.6  # FR-VN-06


class VoiceService:
    entity = "voice_actions"

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        simulator: Any = None,
        second_factor: Any = None,
        publish: Any = None,
    ) -> None:
        self.session = session
        self.sessions = SessionRepository(session)
        self.actions = ActionRepository(session)
        self.directory = AssetDirectory(session)
        self.settings = settings or get_settings()
        self.simulator = simulator
        self._second_factor = second_factor
        self._publish = publish or _valkey_publish
        self.catalogue = load_catalogue()

    # ── Sessions ──────────────────────────────────────────────────────

    def start_session(self, actor: CurrentUser, channel: str, device: str | None, lang: str) -> VoiceSession:
        row = self.sessions.create(
            VoiceSession(user_id=ensure_user(self.session, actor), channel=channel, device=device, lang=lang)
        )
        self.session.commit()
        return row

    def get_session_or_404(self, session_id: uuid.UUID) -> VoiceSession:
        row = self.sessions.get(session_id)
        if row is None:
            raise NotFoundError(f"Voice session {session_id} not found")
        return row

    def session_detail(self, session_id: uuid.UUID) -> dict[str, Any]:
        row = self.get_session_or_404(session_id)
        return {**{c: getattr(row, c) for c in _columns(row)}, "turns": self.sessions.turns(session_id)}

    def recent_sessions(self, actor: CurrentUser, limit: int) -> list[VoiceSession]:
        """An operator sees their own history; a manager or admin sees the floor's."""
        if actor.has_any("manager", "admin"):
            return self.sessions.for_user(None, limit)
        return self.sessions.for_user(ensure_user(self.session, actor), limit)

    def end_session(self, actor: CurrentUser, session_id: uuid.UUID) -> VoiceSession:
        row = self.get_session_or_404(session_id)
        row.ended_at = datetime.now(UTC)
        self.session.commit()
        return row

    def intents(self) -> list[dict[str, Any]]:
        return describe(self.catalogue)

    # ── One turn ──────────────────────────────────────────────────────

    def handle(self, actor: CurrentUser, data: UtteranceIn) -> TurnResponse:
        started = time.perf_counter()
        now = datetime.now(UTC)
        session = (
            self.get_session_or_404(data.session_id)
            if data.session_id
            else self.start_session(actor, data.channel, None, data.lang or "en")
        )
        lang = data.lang or session.lang
        self.actions.expire_stale(now)

        result = route(
            data.text,
            now=now,
            lang=lang,
            endpoint=self.settings.llm_endpoint,
            model=self.settings.llm_model,
            catalogue=self.catalogue,
        )

        if result.control is not None:
            return self._handle_control(actor, session, data, result, now, started)

        turn = self.sessions.add_turn(
            VoiceTurn(
                session_id=session.id,
                transcript=data.text,
                transcript_confidence=data.transcript_confidence,
                stt_ms=data.stt_ms,
                snr_db=data.snr_db,
                intent=result.intent,
                intent_confidence=result.confidence,
                router=result.router,
                router_ms=result.router_ms,
                tier=result.tier,
                slots=_jsonable(result.slots),
            )
        )

        response = self._respond(actor, session, turn, result, data, lang, now)
        turn.response_text = response.text
        turn.citations = _jsonable(response.citations)
        turn.total_ms = response.total_ms = int((time.perf_counter() - started) * 1000)
        self.session.commit()
        return response

    def _respond(
        self,
        actor: CurrentUser,
        session: VoiceSession,
        turn: VoiceTurn,
        result: RouterResult,
        data: UtteranceIn,
        lang: str,
        now: datetime,
    ) -> TurnResponse:
        base = {
            "session_id": session.id,
            "turn_id": turn.id,
            "intent": result.intent,
            "tier": result.tier,
            "router": result.router,
            "confidence": result.confidence,
            "lang": lang,
            "slots": _jsonable(result.slots),
        }

        # FR-VN-06: a transcript the recogniser itself doubts is a question, never an action.
        if data.transcript_confidence is not None and data.transcript_confidence < LOW_TRANSCRIPT_CONFIDENCE:
            suggestions = self._suggest(result.slots.get("asset") or data.text)
            text = (
                narrate.did_you_mean([s.label for s in suggestions], lang)
                if suggestions
                else narrate.not_understood(lang)
            )
            return TurnResponse(**base, text=text, suggestions=suggestions)

        if not result.understood:
            return TurnResponse(**base, text=narrate.compose("help", {"ok": True}, lang))

        try:
            params, ask, suggestions = self._resolve(session, result, now)
        except ProblemError as exc:
            return TurnResponse(**base, text=exc.detail or exc.title)
        if ask is not None:
            return TurnResponse(**base, text=ask, suggestions=suggestions)

        if tiers.needs_confirmation(result.tier):
            return self._read_back(actor, session, turn, result, params, lang, now, base)

        return self._execute_now(actor, session, turn, result, params, lang, base)

    # ── Slot resolution ───────────────────────────────────────────────

    def _resolve(
        self, session: VoiceSession, result: RouterResult, now: datetime
    ) -> tuple[dict[str, Any], str | None, list[Any]]:
        """Spoken slots -> tool parameters. Returns (params, question to ask instead, suggestions)."""
        from app.modules.voice.schemas import Suggestion

        params: dict[str, Any] = dict(result.slots)
        context = self._live_context(session, now)
        lang = session.lang

        spoken = result.slots.get("asset") or result.slots.get("alarm") or result.slots.get("scope")
        scope_slot = "scope" if "scope" in result.slots else "asset"

        if spoken:
            refs = [fuzzy.AssetRef(id=str(i), code=c, name=n) for i, c, n in self.directory.assets()]
            if result.intent == "get_kpi" or "scope" in result.slots:
                refs += [fuzzy.AssetRef(id=str(i), code=c, name=n) for i, c, n in self.directory.lines()]
            match, alternatives = fuzzy.resolve(spoken, refs)
            if match is None:
                options = [Suggestion(label=c.ref.name, value=c.ref.id) for c in alternatives]
                return (
                    params,
                    (
                        narrate.did_you_mean([o.label for o in options], lang)
                        if options
                        else f"I don't know a machine called {spoken}."
                    ),
                    options,
                )
            params["asset_id"] = match.id
            params["asset_label"] = match.name
            if result.intent == "get_kpi":
                params["scope_id"] = match.id
                params["scope"] = "line" if match.id in {str(i) for i, _, _ in self.directory.lines()} else "asset"
                params["scope_label"] = match.name
            self._remember(session, asset_id=match.id, asset_code=match.code, now=now)
        elif context.get("current_asset_id"):
            params["asset_id"] = context["current_asset_id"]
            params["asset_label"] = context.get("current_asset_label")
            if result.intent == "get_kpi":
                params.setdefault("scope_id", context["current_asset_id"])
                params.setdefault("scope", "asset")

        if result.intent == "acknowledge_alarm":
            alarm_id = self._resolve_alarm(params.get("asset_id"), context)
            if alarm_id is None:
                return params, "I can't find an open alarm on that machine.", []
            params["alarm_id"] = alarm_id

        if result.intent == "give_feedback" and context.get("last_explanation_id"):
            params["explanation_id"] = context["last_explanation_id"]

        # Whatever the grammar says a slot is, the tool is the authority on what it cannot run
        # without. Asking beats a 500 when an asset went unresolved and no context could fill it.
        for name in tools.required_arguments(result.intent) - params.keys():
            return params, _ask_for(name), []

        intent = self.catalogue.get(result.intent)
        required = {s.name for s in (intent.slots if intent else ()) if s.required}
        satisfied = set(params) | ({scope_slot} if params.get("asset_id") else set())
        missing = sorted(required - satisfied - {"asset", "alarm", "scope", "verdict", "parameter"})
        if missing:
            return params, f"I need the {missing[0].replace('_', ' ')} as well.", []
        return params, None, []

    def _resolve_alarm(self, asset_id: Any, context: dict[str, Any]) -> str | None:
        if asset_id is None:
            return context.get("last_alarm_id")
        # The same query the status tool runs; one implementation, so the two cannot disagree.
        alarms = tools.open_alarms(
            tools.ToolContext(session=self.session, actor=None, now=datetime.now(UTC)),  # type: ignore[arg-type]
            uuid.UUID(str(asset_id)),
        )
        active = [a for a in alarms if a.status == "active"]
        return str(active[0].id) if active else None

    def _suggest(self, spoken: str) -> list[Any]:
        from app.modules.voice.schemas import Suggestion

        refs = [fuzzy.AssetRef(id=str(i), code=c, name=n) for i, c, n in self.directory.assets()]
        return [Suggestion(label=c.ref.name, value=c.ref.id) for c in fuzzy.rank(spoken, refs)]

    # ── Dialogue context (FR-VN-05) ───────────────────────────────────

    def _live_context(self, session: VoiceSession, now: datetime) -> dict[str, Any]:
        """The session context, or an empty one once the two-minute silence has elapsed."""
        context = dict(session.context or {})
        touched = context.get("touched_at")
        if touched and now - datetime.fromisoformat(touched) > CONTEXT_TTL:
            return {}
        return context

    def _remember(self, session: VoiceSession, *, now: datetime, **values: Any) -> None:
        context = self._live_context(session, now)
        if values.get("asset_id"):
            context["current_asset_id"] = values["asset_id"]
            context["current_asset_code"] = values.get("asset_code")
        for key in ("last_prediction_id", "last_explanation_id", "last_alarm_id"):
            if values.get(key):
                context[key] = values[key]
        context["touched_at"] = now.isoformat()
        session.context = context

    # ── Tier execution ────────────────────────────────────────────────

    def _execute_now(
        self,
        actor: CurrentUser,
        session: VoiceSession,
        turn: VoiceTurn,
        result: RouterResult,
        params: dict[str, Any],
        lang: str,
        base: dict[str, Any],
    ) -> TurnResponse:
        context = tools.ToolContext(
            session=self.session,
            actor=actor,
            now=datetime.now(UTC),
            lang=lang,
            session_id=session.id,
            context=dict(session.context or {}),
            simulator=self.simulator,
            publish=self._publish,
        )
        try:
            output = tools.TOOLS[result.intent](context, **params)
        except ProblemError as exc:
            return TurnResponse(**base, text=exc.detail or exc.title)

        self._remember(
            session,
            now=context.now,
            asset_id=output.get("asset_id"),
            asset_code=output.get("asset_code"),
            last_prediction_id=output.get("prediction_id"),
            last_explanation_id=output.get("explanation_id"),
        )
        hypothetical = result.tier == "T1"
        return TurnResponse(
            **base,
            text=narrate.compose(result.intent, output, lang, hypothetical=hypothetical),
            citations=narrate.citations(output),
            hypothetical=hypothetical,
            navigate=output if result.intent == "navigate_dashboard" else None,
        )

    def _read_back(
        self,
        actor: CurrentUser,
        session: VoiceSession,
        turn: VoiceTurn,
        result: RouterResult,
        params: dict[str, Any],
        lang: str,
        now: datetime,
        base: dict[str, Any],
    ) -> TurnResponse:
        if tiers.needs_second_factor(result.tier) and not self.settings.allow_t3:
            return TurnResponse(**base, text="Actuation is disabled on this installation.")

        readback = tiers.readback(result.intent, {**params, **result.slots}, lang)
        action = self.actions.create(
            VoiceAction(
                turn_id=turn.id,
                tool=result.intent,
                params=_jsonable(params),
                tier=result.tier,
                readback=readback,
                status="pending",
                expires_at=now + timedelta(seconds=tiers.CONFIRM_WINDOW_S),
            )
        )
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=action.id,
            action="read_back",
            after={"tool": action.tool, "tier": action.tier, "readback": readback},
        )
        from app.modules.voice.schemas import ActionOut

        return TurnResponse(**base, text=readback, action=ActionOut.model_validate(action))

    def _handle_control(
        self,
        actor: CurrentUser,
        session: VoiceSession,
        data: UtteranceIn,
        result: RouterResult,
        now: datetime,
        started: float,
    ) -> TurnResponse:
        """ "confirm" / "cancel" / "repeat" act on the session's one pending read-back."""
        turn = self.sessions.add_turn(
            VoiceTurn(
                session_id=session.id,
                transcript=data.text,
                intent=f"control:{result.control}",
                router=result.router,
                router_ms=result.router_ms,
                intent_confidence=result.confidence,
            )
        )
        lang = data.lang or session.lang
        base = {
            "session_id": session.id,
            "turn_id": turn.id,
            "intent": f"control:{result.control}",
            "tier": "T0",
            "router": result.router,
            "confidence": result.confidence,
            "lang": lang,
        }

        if result.control == "repeat":
            previous = self.sessions.last_turn(session.id)
            text = (previous.response_text if previous else None) or narrate.not_understood(lang)
            turn.response_text = text
            self.session.commit()
            return TurnResponse(**base, text=text, total_ms=int((time.perf_counter() - started) * 1000))

        pending = self.actions.pending_for_session(session.id, now)
        if pending is None:
            turn.response_text = "There is nothing waiting for confirmation."
            self.session.commit()
            return TurnResponse(**base, text=turn.response_text)

        if result.control == "cancel":
            response = self.cancel(actor, pending.id)
        else:
            response = self.confirm(actor, pending.id, pin=None, lang=lang)
        turn.response_text = response["text"]
        self.session.commit()
        from app.modules.voice.schemas import ActionOut

        return TurnResponse(
            **base,
            text=response["text"],
            action=ActionOut.model_validate(response["action"]),
            total_ms=int((time.perf_counter() - started) * 1000),
        )

    # ── Confirmation (FR-VN-07) ───────────────────────────────────────

    def confirm(self, actor: CurrentUser, action_id: uuid.UUID, pin: str | None, lang: str = "en") -> dict[str, Any]:
        action = self._action_or_404(action_id)
        now = datetime.now(UTC)
        if action.status != "pending":
            raise ConflictError(f"That action is already {action.status}")
        if action.expires_at is not None and action.expires_at <= now:
            action.status = "expired"
            self.session.commit()
            raise ConflictError("The confirmation window closed. Please say it again.")

        if tiers.needs_second_factor(action.tier):
            if not self.settings.allow_t3:
                action.status = "rejected"
                self.session.commit()
                raise ForbiddenError("Actuation is disabled on this installation")
            if not self._second_factor_ok(actor, pin):
                action.status = "rejected"
                action.second_factor_ok = False
                write_audit(
                    self.session, actor=actor, entity=self.entity, entity_id=action.id, action="second_factor_failed"
                )
                self.session.commit()
                raise ForbiddenError("That PIN is not correct")
            action.second_factor_ok = True

        errors = self._validate(action, now)
        if errors:
            action.status = "rejected"
            action.validation_errors = errors
            write_audit(
                self.session, actor=actor, entity=self.entity, entity_id=action.id, action="rejected", after=errors
            )
            self.session.commit()
            return {"action": action, "text": "; ".join(errors.values())}

        action.status = "confirmed"
        action.confirmed_at = now
        context = tools.ToolContext(
            session=self.session,
            actor=actor,
            now=now,
            lang=lang,
            session_id=self._session_id_of(action),
            simulator=self.simulator,
            publish=self._publish,
        )
        try:
            output = tools.TOOLS[action.tool](context, **revive_params(action.params))
        except ProblemError as exc:
            action.status = "failed"
            action.error = exc.detail or exc.title
            write_audit(
                self.session,
                actor=actor,
                entity=self.entity,
                entity_id=action.id,
                action="failed",
                after={"error": action.error},
            )
            self.session.commit()
            return {"action": action, "text": action.error}

        action.status = "executed"
        action.executed_at = now
        action.result = _jsonable(output)
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=action.id,
            action="executed",
            after={"tool": action.tool, "result": action.result},
        )
        self.session.commit()
        return {"action": action, "text": narrate.compose(action.tool, output, lang)}

    def cancel(self, actor: CurrentUser, action_id: uuid.UUID) -> dict[str, Any]:
        action = self._action_or_404(action_id)
        if action.status != "pending":
            raise ConflictError(f"That action is already {action.status}")
        action.status = "cancelled"
        write_audit(self.session, actor=actor, entity=self.entity, entity_id=action.id, action="cancelled")
        self.session.commit()
        return {"action": action, "text": "Cancelled."}

    def _action_or_404(self, action_id: uuid.UUID) -> VoiceAction:
        action = self.actions.get(action_id)
        if action is None:
            raise NotFoundError(f"Voice action {action_id} not found")
        return action

    def _session_id_of(self, action: VoiceAction) -> uuid.UUID | None:
        turn = self.session.get(VoiceTurn, action.turn_id)
        return turn.session_id if turn else None

    def _second_factor_ok(self, actor: CurrentUser, pin: str | None) -> bool:
        from app.core.security import get_second_factor

        checker = self._second_factor or get_second_factor()
        return bool(pin) and checker.verify(actor.sub, pin or "")

    def _validate(self, action: VoiceAction, now: datetime) -> dict[str, str]:
        """Re-check the parameters against twin state at confirmation time (FR-VN-07).

        The read-back and the execution are separated by a human decision, so nothing established
        before the read-back may be assumed still true after it.
        """
        errors: dict[str, str] = {}
        params = revive_params(action.params)

        asset_id = params.get("asset_id")
        if asset_id:
            from app.modules.assets.models import Asset

            asset = self.session.get(Asset, uuid.UUID(str(asset_id)))
            if asset is None or asset.deleted_at is not None:
                errors["asset"] = "That machine is no longer in the registry."

        when = params.get("when") or params.get("planned_start")
        if when:
            planned = when if isinstance(when, datetime) else datetime.fromisoformat(str(when))
            if planned <= now:
                errors["when"] = "That time is in the past."

        technician_id = params.get("technician_id")
        if technician_id and when:
            planned = when if isinstance(when, datetime) else datetime.fromisoformat(str(when))
            if not self._technician_available(uuid.UUID(str(technician_id)), planned):
                errors["technician"] = "That technician is not available then."

        if action.tool == "acknowledge_alarm" and params.get("alarm_id"):
            from app.modules.telemetry.models import Alarm

            alarm = self.session.get(Alarm, uuid.UUID(str(params["alarm_id"])))
            if alarm is None or alarm.status != "active":
                errors["alarm"] = "That alarm is no longer open."
        return errors

    def _technician_available(self, technician_id: uuid.UUID, at: datetime) -> bool:
        technician = self.session.get(Technician, technician_id)
        if technician is None or technician.deleted_at is not None:
            return False
        from sqlalchemy import select

        window = self.session.scalars(
            select(TechnicianAvailability).where(
                TechnicianAvailability.technician_id == technician_id,
                TechnicianAvailability.kind == "available",
                TechnicianAvailability.starts_at <= at,
                TechnicianAvailability.ends_at > at,
            )
        ).first()
        # No availability rows at all means the roster is not maintained, not that nobody can work.
        any_rows = self.session.scalars(
            select(TechnicianAvailability).where(TechnicianAvailability.technician_id == technician_id).limit(1)
        ).first()
        return window is not None or any_rows is None

    # ── Intent suite (FR-NL-06) ───────────────────────────────────────

    def seed_intent_examples(self) -> int:
        from twinvoice_nlu.suite import generate

        repo = IntentExampleRepository(self.session)
        rows = [
            IntentExample(
                intent=u.intent,
                lang=u.lang,
                text=u.text,
                slots=u.slots or None,
                noise_variant=u.noise_variant,
                split=u.split,
            )
            for u in _deduplicate(generate())
        ]
        count = repo.replace_all(rows)
        self.session.commit()
        return count

    def suite_accuracy(self) -> list[dict[str, Any]]:
        """Measured, not cached: the router's accuracy against the stored labelled utterances.

        Slots are scored alongside intents. An utterance routed to the right intent with the wrong
        machine still produces the wrong action, so intent accuracy on its own overstates the router.
        """
        rows = IntentExampleRepository(self.session).all()
        now = datetime.now(UTC)
        by_split: dict[str, list[IntentExample]] = {}
        for row in rows:
            by_split.setdefault(row.split, []).append(row)
        out = []
        for split, group in sorted(by_split.items()):
            correct = 0
            slots_matched = slots_expected = 0
            for row in group:
                result = route(row.text, now=now, catalogue=self.catalogue)
                correct += result.intent == row.intent
                matched, expected = score_slots(
                    Utterance(row.text, row.intent, row.lang, row.noise_variant, row.split, row.slots or {}),
                    result.slots,
                    self.catalogue.get(row.intent),
                )
                slots_matched += matched
                slots_expected += expected
            out.append(
                {
                    "split": split,
                    "total": len(group),
                    "correct": correct,
                    "accuracy": round(correct / len(group), 4) if group else 0.0,
                    "slots_total": slots_expected,
                    "slots_correct": slots_matched,
                    "slot_accuracy": round(slots_matched / slots_expected, 4) if slots_expected else None,
                }
            )
        return out


# What to say when a tool needs an argument the utterance never supplied.
ASK_FOR = {
    "asset_id": "Which machine do you mean?",
    "alarm_id": "Which alarm do you mean?",
    "explanation_id": "Which prediction should I explain?",
    "scope_id": "For which machine or line?",
    "task": "What should the work order say?",
}


def _ask_for(argument: str) -> str:
    return ASK_FOR.get(argument, f"I need the {argument.replace('_id', '').replace('_', ' ')} as well.")


def revive_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """Undo the JSONB round trip for the parameters a tool expects as datetimes."""
    revived = dict(params or {})
    for key in DATETIME_PARAMS & revived.keys():
        value = revived[key]
        if isinstance(value, str):
            try:
                revived[key] = datetime.fromisoformat(value)
            except ValueError:
                revived.pop(key)
    return revived


def _deduplicate(utterances: list[Any]) -> list[Any]:
    """The unique index is (intent, lang, text, split); noise can regenerate a clean utterance."""
    seen: set[tuple[str, str, str, str]] = set()
    unique = []
    for u in utterances:
        key = (u.intent, u.lang, u.text, u.split)
        if key not in seen:
            seen.add(key)
            unique.append(u)
    return unique


def _columns(row: Any) -> list[str]:
    from sqlalchemy import inspect

    return [attr.key for attr in inspect(row).mapper.column_attrs]


def _jsonable(value: Any) -> Any:
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(value)


def _valkey_publish(channel: str, kind: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget onto the channel `WsHub` already subscribes to; a failure never fails a turn."""
    try:
        with valkey.Valkey.from_url(get_settings().valkey_url, socket_timeout=2) as client:
            client.publish(channel, json.dumps({"kind": kind, "payload": _jsonable(payload)}))
    except Exception:
        log.warning("voice event publish failed", extra={"channel": channel}, exc_info=True)


__all__ = ["CONTEXT_TTL", "UnprocessableError", "VoiceService"]
