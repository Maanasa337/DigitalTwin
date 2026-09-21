"""Service layer for telemetry queries, alarm rules, and alarm lifecycle (M3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.core.audit import snapshot, write_audit
from app.core.errors import NotFoundError, UnprocessableError
from app.core.security import CurrentUser
from app.modules.assets.models import Asset, Sensor
from app.modules.telemetry.models import Alarm, AlarmAction, AlarmRule
from app.modules.telemetry.repository import AlarmRepository, AlarmRuleRepository, TelemetryRepository
from app.modules.telemetry.schemas import (
    AggLevel,
    AlarmActionCreate,
    AlarmRuleCreate,
    AlarmRuleUpdate,
    TelemetryAggPoint,
    TelemetryLatestResponse,
    TelemetryLatestValue,
    TelemetryPoint,
    TelemetrySeries,
)

HOUR_6 = timedelta(hours=6)
DAY_7 = timedelta(days=7)


class TelemetryService:
    """Query telemetry with automatic aggregation-tier selection."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = TelemetryRepository(session)

    def _resolve_sensors(self, asset_id: uuid.UUID, sensor_codes: list[str] | None) -> list[Sensor]:
        from sqlalchemy import select

        stmt = select(Sensor).where(Sensor.asset_id == asset_id, Sensor.deleted_at.is_(None))
        if sensor_codes:
            stmt = stmt.where(Sensor.code.in_(sensor_codes))
        return list(self.session.scalars(stmt))

    def query(
        self,
        asset_id: uuid.UUID,
        sensor_codes: list[str] | None,
        start: datetime,
        end: datetime,
        agg: AggLevel | None = None,
    ) -> list[TelemetrySeries]:
        sensors = self._resolve_sensors(asset_id, sensor_codes)
        if not sensors:
            return []
        sensor_ids = [s.id for s in sensors]
        sensor_map = {s.id: s for s in sensors}

        span = end - start
        if agg is None:
            agg = AggLevel.RAW if span <= HOUR_6 else (AggLevel.ONE_MIN if span <= DAY_7 else AggLevel.ONE_HOUR)

        if agg == AggLevel.RAW:
            rows = self.repo.query_raw(sensor_ids, start, end)
        elif agg == AggLevel.ONE_MIN:
            rows = self.repo.query_1m(sensor_ids, start, end)
        else:
            rows = self.repo.query_1h(sensor_ids, start, end)

        # Group by sensor
        by_sensor: dict[uuid.UUID, list[dict[str, Any]]] = {sid: [] for sid in sensor_ids}
        for row in rows:
            sid = row["sensor_id"]
            if sid in by_sensor:
                by_sensor[sid].append(row)

        result: list[TelemetrySeries] = []
        for sid, points in by_sensor.items():
            s = sensor_map[sid]
            pts: list[TelemetryPoint] | list[TelemetryAggPoint]
            if agg == AggLevel.RAW:
                pts = [TelemetryPoint(time=p["time"], value=p["value"], quality=p["quality"]) for p in points]
            else:
                pts = [
                    TelemetryAggPoint(
                        bucket=p["time"], avg=p["avg"], min=p["min"], max=p["max"], std=p["std"], n=p["n"]
                    )
                    for p in points
                ]
            result.append(TelemetrySeries(sensor_id=str(sid), metric_name=s.metric_name, unit=s.unit, points=pts))
        return result

    def latest(self, asset_id: uuid.UUID) -> TelemetryLatestResponse:
        asset = self.session.get(Asset, asset_id)
        if asset is None:
            raise NotFoundError(f"Asset {asset_id} not found")
        rows = self.repo.latest_per_asset(asset_id)
        values = [
            TelemetryLatestValue(
                sensor_id=str(r["sensor_id"]),
                metric_name=r["metric_name"],
                name=r["name"],
                unit=r["unit"],
                value=r["value"],
                quality=r["quality"] or 0,
                time=r["time"],
            )
            for r in rows
        ]
        return TelemetryLatestResponse(asset_code=asset.code, values=values)


class AlarmRuleService:
    entity = "alarm_rules"

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = AlarmRuleRepository(session)

    def list_rules(self, params: PageParams) -> tuple[list[AlarmRule], int]:
        return self.repo.list(params)

    def get_or_404(self, rule_id: uuid.UUID) -> AlarmRule:
        obj = self.repo.get(rule_id)
        if obj is None:
            raise NotFoundError(f"Alarm rule {rule_id} not found")
        return obj

    def create_rule(self, actor: CurrentUser, data: AlarmRuleCreate) -> AlarmRule:
        rule = AlarmRule(**data.model_dump())
        self.repo.create(rule)
        write_audit(
            self.session, actor=actor, entity=self.entity, entity_id=rule.id, action="create", after=snapshot(rule)
        )
        self.session.commit()
        return rule

    def update_rule(self, actor: CurrentUser, rule_id: uuid.UUID, data: AlarmRuleUpdate) -> AlarmRule:
        rule = self.get_or_404(rule_id)
        before = snapshot(rule)
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            return rule
        self.repo.update(rule, updates)
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=rule.id,
            action="update",
            before=before,
            after=snapshot(rule),
        )
        self.session.commit()
        return rule


class AlarmService:
    entity = "alarms"

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = AlarmRepository(session)

    def list_alarms(
        self,
        params: PageParams,
        severity: str | None = None,
        status: str | None = None,
        asset_id: uuid.UUID | None = None,
    ) -> tuple[list[Alarm], int]:
        filters = []
        if severity:
            filters.append(Alarm.severity == severity)
        if status:
            filters.append(Alarm.status == status)
        if asset_id:
            filters.append(Alarm.asset_id == asset_id)
        return self.repo.list_alarms(params, filters or None)

    def get_or_404(self, alarm_id: uuid.UUID) -> Alarm:
        alarm = self.repo.get(alarm_id)
        if alarm is None:
            raise NotFoundError(f"Alarm {alarm_id} not found")
        return alarm

    def perform_action(self, actor: CurrentUser, alarm_id: uuid.UUID, data: AlarmActionCreate) -> Alarm:
        alarm = self.get_or_404(alarm_id)

        if data.action == "ack":
            if alarm.status != "active":
                raise UnprocessableError("Can only acknowledge active alarms")
            alarm.status = "acknowledged"
            alarm.acknowledged_by = None  # filled from audit user lookup
            alarm.acknowledged_at = datetime.now(UTC)
        elif data.action == "assign":
            if data.assigned_to is None:
                raise UnprocessableError("assigned_to required for assign action")
            alarm.assigned_to = data.assigned_to
        elif data.action == "shelve":
            hours = data.shelve_hours or 4
            alarm.status = "shelved"
            alarm.shelved_until = datetime.now(UTC) + timedelta(hours=hours)
        elif data.action == "unshelve":
            alarm.status = "acknowledged" if alarm.acknowledged_at else "active"
            alarm.shelved_until = None
        elif data.action == "clear":
            alarm.status = "cleared"
            alarm.cleared_at = datetime.now(UTC)

        action = AlarmAction(alarm_id=alarm.id, action=data.action, note=data.note)
        self.repo.add_action(action)
        self.session.flush()

        write_audit(self.session, actor=actor, entity=self.entity, entity_id=alarm.id, action=data.action)
        self.session.commit()
        return alarm

    def bulk_ack(self, actor: CurrentUser, alarm_ids: list[uuid.UUID]) -> int:
        from app.core.audit import ensure_user

        user_id = ensure_user(self.session, actor)
        count = self.repo.bulk_ack(alarm_ids, user_id)
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=None,
            action="bulk_ack",
            after={"count": count, "ids": [str(i) for i in alarm_ids]},
        )
        self.session.commit()
        return count
