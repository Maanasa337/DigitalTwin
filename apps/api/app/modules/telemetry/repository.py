"""Repository layer for telemetry queries, alarm rules, and alarms (M3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, Select, func, select, text, update
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.common.repository import CrudRepository
from app.modules.telemetry.models import Alarm, AlarmAction, AlarmRule


class TelemetryRepository:
    """Raw and aggregated telemetry queries against hypertables and continuous aggregates."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def query_raw(
        self,
        sensor_ids: list[uuid.UUID],
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        stmt = text("""
            SELECT time, sensor_id, value, quality
            FROM telemetry
            WHERE sensor_id = ANY(:ids) AND time >= :start AND time < :end
            ORDER BY time
        """)
        rows = self.session.execute(stmt, {"ids": sensor_ids, "start": start, "end": end}).mappings().all()
        return [dict(r) for r in rows]

    def query_1m(
        self,
        sensor_ids: list[uuid.UUID],
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        stmt = text("""
            SELECT bucket AS time, sensor_id, avg, min, max, std, n
            FROM telemetry_1m
            WHERE sensor_id = ANY(:ids) AND bucket >= :start AND bucket < :end
            ORDER BY bucket
        """)
        rows = self.session.execute(stmt, {"ids": sensor_ids, "start": start, "end": end}).mappings().all()
        return [dict(r) for r in rows]

    def query_1h(
        self,
        sensor_ids: list[uuid.UUID],
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        stmt = text("""
            SELECT bucket AS time, sensor_id, avg, min, max, std, n
            FROM telemetry_1h
            WHERE sensor_id = ANY(:ids) AND bucket >= :start AND bucket < :end
            ORDER BY bucket
        """)
        rows = self.session.execute(stmt, {"ids": sensor_ids, "start": start, "end": end}).mappings().all()
        return [dict(r) for r in rows]

    def latest_per_asset(self, asset_id: uuid.UUID) -> list[dict[str, Any]]:
        """Latest value for every sensor belonging to the asset."""
        stmt = text("""
            SELECT DISTINCT ON (s.id)
                   s.id AS sensor_id, s.metric_name, s.name, s.unit,
                   t.value, t.quality, t.time
            FROM sensors s
            LEFT JOIN LATERAL (
                SELECT value, quality, time
                FROM telemetry
                WHERE sensor_id = s.id
                ORDER BY time DESC LIMIT 1
            ) t ON true
            WHERE s.asset_id = :asset_id AND s.deleted_at IS NULL
            ORDER BY s.id
        """)
        rows = self.session.execute(stmt, {"asset_id": asset_id}).mappings().all()
        return [dict(r) for r in rows]

    def batch_insert(self, rows: list[dict[str, Any]]) -> int:
        """Insert telemetry rows using executemany for performance."""
        if not rows:
            return 0
        stmt = text("""
            INSERT INTO telemetry (time, sensor_id, value, quality)
            VALUES (:time, :sensor_id, :value, :quality)
        """)
        self.session.execute(stmt, rows)
        return len(rows)


class AlarmRuleRepository(CrudRepository["AlarmRule"]):
    model = AlarmRule
    sortable = frozenset({"created_at", "severity", "kind"})

    def enabled_for_sensor(self, sensor_id: uuid.UUID) -> list[AlarmRule]:
        return list(
            self.session.scalars(
                self._select().where(
                    AlarmRule.sensor_id == sensor_id,
                    AlarmRule.enabled.is_(True),
                )
            )
        )

    def enabled_for_asset(self, asset_id: uuid.UUID) -> list[AlarmRule]:
        return list(
            self.session.scalars(
                self._select().where(
                    AlarmRule.asset_id == asset_id,
                    AlarmRule.enabled.is_(True),
                )
            )
        )


class AlarmRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, alarm_id: uuid.UUID) -> Alarm | None:
        return self.session.get(Alarm, alarm_id)

    def list_alarms(
        self,
        params: PageParams,
        filters: list[ColumnElement[bool]] | None = None,
    ) -> tuple[list[Alarm], int]:
        stmt: Select[tuple[Alarm]] = select(Alarm)
        if filters:
            stmt = stmt.where(*filters)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        sort_col = Alarm.raised_at.desc()
        items = list(
            self.session.scalars(stmt.order_by(sort_col).offset((params.page - 1) * params.size).limit(params.size))
        )
        return items, total

    def active_for_rule_and_asset(self, rule_id: uuid.UUID, asset_id: uuid.UUID) -> Alarm | None:
        return self.session.scalars(
            select(Alarm).where(
                Alarm.rule_id == rule_id,
                Alarm.asset_id == asset_id,
                Alarm.status.in_(("active", "acknowledged")),
            )
        ).first()

    def create(self, alarm: Alarm) -> Alarm:
        self.session.add(alarm)
        self.session.flush()
        return alarm

    def add_action(self, action: AlarmAction) -> AlarmAction:
        self.session.add(action)
        self.session.flush()
        return action

    def clear_alarm(self, alarm: Alarm) -> None:
        alarm.status = "cleared"
        alarm.cleared_at = func.now()  # type: ignore[assignment]
        self.session.flush()

    def bulk_ack(self, alarm_ids: list[uuid.UUID], actor_id: uuid.UUID) -> int:
        result = self.session.execute(
            update(Alarm)
            .where(Alarm.id.in_(alarm_ids), Alarm.status == "active")
            .values(status="acknowledged", acknowledged_by=actor_id, acknowledged_at=func.now())
        )
        self.session.flush()
        return cast(CursorResult[Any], result).rowcount
