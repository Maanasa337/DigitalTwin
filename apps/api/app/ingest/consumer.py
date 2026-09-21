"""MQTT consumer: Sparkplug B → TimescaleDB + Ditto + Valkey fan-out + alarm engine.

Run as: ``python -m app.ingest``
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import paho.mqtt.client as mqtt
import valkey as valkey_lib
from paho.mqtt.enums import CallbackAPIVersion
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.models  # noqa: F401  — registers every table so cross-module FKs resolve in the consumer
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.ditto import DittoClient
from app.ingest.alarm_engine import AlarmEngine
from app.modules.analytics.models import Tariff
from app.modules.analytics.repository import TariffRepository
from app.modules.telemetry.models import Alarm, AssetStateEvent

log = logging.getLogger(__name__)

BATCH_SIZE = 500
FLUSH_INTERVAL_S = 0.25
SPARKPLUG_TOPIC = "spBv1.0/#"

# Metrics the simulator publishes per asset rather than per sensor. `state`, the two counters and
# `cycle_time_s` have no sensor row at all; `power_kw` and `power_factor` do, and are read twice —
# once as telemetry, once to build the energy reading.
ASSET_METRICS = frozenset(
    {"state", "good_count", "reject_count", "cycle_time_s", "energy_kwh", "power_kw", "power_factor"}
)
VALID_STATES = frozenset({"RUNNING", "IDLE", "DOWN", "MAINTENANCE", "UNKNOWN"})
# Matches the simulator's electrical model (sim/energy.py), so current derived here agrees with it.
LINE_VOLTAGE_V = 415.0
SQRT_3 = 3.0**0.5

# Cache of (asset_code, metric_name) → sensor row info. Metric names are only unique *within* an
# asset — every machine publishes `power_kw` and `load_pct` — so the asset code has to be part of
# the key or one asset's sensor silently swallows the whole fleet's readings.
MetricKey = tuple[str, str]
MetricMap = dict[MetricKey, dict[str, Any]]


def _build_metric_map(session: Session) -> MetricMap:
    """Build an (asset_code, metric_name) → sensor info lookup from the DB."""
    rows = (
        session.execute(
            text("""
            SELECT s.id AS sensor_id, s.metric_name, s.asset_id, a.code AS asset_code,
                   s.code AS sensor_code, s.name, s.unit
            FROM sensors s
            JOIN assets a ON a.id = s.asset_id
            WHERE s.deleted_at IS NULL AND a.deleted_at IS NULL
        """)
        )
        .mappings()
        .all()
    )
    return {(r["asset_code"], r["metric_name"]): dict(r) for r in rows}


def _as_float(value: Any) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _counter_delta(previous: dict[str, float], key: str, current: float | None) -> float:
    """Difference against the last reading, treating a counter reset as a fresh start."""
    if current is None:
        return 0.0
    last = previous.get(key)
    previous[key] = current
    if last is None or current < last:
        return 0.0
    return current - last


def _build_asset_map(session: Session) -> dict[str, uuid.UUID]:
    """asset_code → asset_id, for the asset-level metrics that carry no sensor row."""
    rows = session.execute(text("SELECT id, code FROM assets WHERE deleted_at IS NULL")).all()
    return {row[1]: row[0] for row in rows}


def _load_last_states(session: Session) -> dict[uuid.UUID, str]:
    """The state each asset was last known to be in, so a restart does not re-emit a transition."""
    rows = session.execute(
        text("SELECT DISTINCT ON (asset_id) asset_id, state FROM asset_state_events ORDER BY asset_id, time DESC")
    ).all()
    return {row[0]: row[1] for row in rows}


def _load_tariffs(session: Session) -> dict[uuid.UUID, tuple[str, list[Tariff]]]:
    """Tariff windows per asset, paired with the plant timezone they are expressed in."""
    rows = session.execute(
        text("""
        SELECT a.id AS asset_id, p.timezone, t.id AS tariff_id
        FROM tariffs t
        JOIN plants p ON p.id = t.plant_id
        JOIN lines l ON l.plant_id = p.id
        JOIN assets a ON a.line_id = l.id
        WHERE t.deleted_at IS NULL AND a.deleted_at IS NULL
        """)
    ).all()
    if not rows:
        return {}
    tariffs = {t.id: t for t in TariffRepository(session).all_active()}
    by_asset: dict[uuid.UUID, tuple[str, list[Tariff]]] = {}
    for asset_id, timezone, tariff_id in rows:
        tariff = tariffs.get(tariff_id)
        if tariff is not None:
            by_asset.setdefault(asset_id, (timezone, []))[1].append(tariff)
    return by_asset


def _tariff_rate(entry: tuple[str, list[Tariff]] | None, at: datetime) -> Decimal | None:
    """The rate in force at `at`, evaluated in plant-local time; None when no window covers it."""
    if entry is None:
        return None
    timezone, tariffs = entry
    rate = TariffRepository.rate_at(tariffs, at.astimezone(ZoneInfo(timezone)))
    return Decimal(str(rate)) if rate else None


def _load_alarm_rules(session: Session) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Load enabled alarm rules grouped by sensor_id."""
    rows = (
        session.execute(
            text("""
            SELECT id, sensor_id, asset_id, kind, params, severity
            FROM alarm_rules
            WHERE enabled = true AND deleted_at IS NULL
        """)
        )
        .mappings()
        .all()
    )
    by_sensor: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        row_dict = dict(r)
        if r["sensor_id"]:
            by_sensor[r["sensor_id"]].append(row_dict)
    return dict(by_sensor)


class IngestConsumer:
    """Sparkplug B MQTT consumer with batched TimescaleDB inserts, Ditto sync, and alarm evaluation."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._session_factory = get_sessionmaker()
        self._buffer: list[dict[str, Any]] = []
        self._buffer_lock = threading.Lock()
        self._last_flush = time.monotonic()
        self._energy_buffer: list[dict[str, Any]] = []
        self._production_buffer: list[dict[str, Any]] = []
        self._metric_map: MetricMap = {}
        self._asset_map: dict[str, uuid.UUID] = {}
        self._tariffs: dict[uuid.UUID, tuple[str, list[Tariff]]] = {}
        self._alarm_rules: dict[uuid.UUID, list[dict[str, Any]]] = {}
        # The simulator publishes monotonic counters; the fact tables want per-interval deltas, so
        # we keep the previous reading per asset and emit the difference.
        self._last_counters: dict[uuid.UUID, dict[str, float]] = {}
        self._last_state: dict[uuid.UUID, str] = {}
        self._valkey = valkey_lib.from_url(self._settings.valkey_url)
        self._alarm_engine = AlarmEngine(self._valkey)
        self._ditto = DittoClient(self._settings.ditto_url, self._settings.ditto_subject)
        self._running = False

    def start(self) -> None:
        """Start the consumer loop."""
        log.info("ingest consumer starting")
        self._refresh_caches()
        self._running = True

        client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=f"twinvoice-ingest-{uuid.uuid4().hex[:8]}",
            protocol=mqtt.MQTTv5,
        )
        client.reconnect_delay_set(1, 30)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.connect(self._settings.mqtt_host, self._settings.mqtt_port, keepalive=30)

        # Periodic flush thread
        flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        flush_thread.start()

        # Cache refresh thread (every 60s)
        refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        refresh_thread.start()

        log.info("ingest consumer connected, entering loop")
        try:
            client.loop_forever()
        except KeyboardInterrupt:
            log.info("ingest consumer shutting down")
        finally:
            self._running = False
            self._flush_buffer()
            client.disconnect()
            self._ditto.close()

    def _on_connect(self, client: mqtt.Client, _userdata: Any, _flags: Any, rc: Any, _props: Any = None) -> None:
        log.info("MQTT connected, subscribing to %s", SPARKPLUG_TOPIC)
        client.subscribe(SPARKPLUG_TOPIC, qos=1)

    def _on_message(self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            self._process_message(msg.topic, msg.payload)
        except Exception:
            log.exception("error processing message on %s", msg.topic)

    def _process_message(self, topic: str, payload: bytes) -> None:
        from twinvoice_contracts.sparkplug import decode_payload, parse_topic

        parsed = parse_topic(topic)
        if parsed is None:
            return

        # Only process DDATA and DBIRTH messages for telemetry
        if parsed.message_type not in ("DDATA", "DBIRTH"):
            if parsed.message_type == "DBIRTH":
                self._refresh_caches()
            return

        decoded = decode_payload(payload)
        asset_code = parsed.device_id
        if not asset_code:
            return

        now = datetime.now(UTC)
        asset_id = self._asset_map.get(asset_code)
        telemetry_rows: list[dict[str, Any]] = []
        ditto_patch: dict[str, Any] = {}
        live_metrics: dict[str, dict[str, Any]] = {}
        # Asset-level metrics carry no sensor row, so they are collected here and turned into
        # energy_readings / production_counts / asset_state_events once the payload is drained.
        asset_metrics: dict[str, Any] = {}

        for metric in decoded["metrics"]:
            metric_name = metric["name"]
            value = metric.get("value")
            if value is None or metric_name.startswith("Node Control"):
                continue

            bare = metric_name.split(".")[-1]
            if bare in ASSET_METRICS:
                asset_metrics[bare] = value
                if bare == "state":
                    live_metrics[metric_name] = {"v": str(value), "u": ""}
                    ditto_patch[metric_name] = {"v": str(value), "u": "", "t": now.isoformat()}
                    continue

            info = self._metric_map.get((asset_code, metric_name))
            if info is None:
                # Try prefixed with asset code
                full_name = f"{asset_code}.{metric_name}" if "." not in metric_name else metric_name
                info = self._metric_map.get((asset_code, full_name))
                if info is None:
                    continue

            # Numeric telemetry
            try:
                float_value = float(value)
            except (TypeError, ValueError):
                continue

            quality = 192
            props = metric.get("properties", {})
            raw_quality = _as_float(props.get("Quality"))
            if raw_quality is not None:
                quality = int(raw_quality)

            metric_time = datetime.fromtimestamp(
                (metric.get("timestamp") or decoded.get("timestamp") or time.time_ns() // 1_000_000) / 1000,
                tz=UTC,
            )

            telemetry_rows.append(
                {
                    "time": metric_time,
                    "sensor_id": info["sensor_id"],
                    "value": float_value,
                    "quality": quality,
                }
            )

            # Ditto patch
            ditto_patch[metric_name] = {"v": float_value, "u": info.get("unit", ""), "t": metric_time.isoformat()}

            # Live fan-out payload
            live_metrics[metric_name] = {"v": float_value, "u": info.get("unit", "")}

            # Run alarm engine
            sensor_id = info["sensor_id"]
            rules = self._alarm_rules.get(sensor_id, [])
            for rule in rules:
                alarm_data = None
                if rule["kind"] == "threshold":
                    alarm_data = self._alarm_engine.evaluate_threshold(
                        rule, sensor_id, info["asset_id"], float_value, metric_name, metric_time
                    )
                elif rule["kind"] == "adaptive":
                    alarm_data = self._alarm_engine.evaluate_adaptive(
                        rule, sensor_id, info["asset_id"], float_value, metric_name, metric_time
                    )

                if alarm_data:
                    self._raise_alarm(alarm_data)

        # Asset-level facts: state transitions, production and energy
        if asset_id is not None and asset_metrics:
            self._handle_asset_metrics(asset_id, asset_metrics, now)

        # Buffer telemetry rows
        if telemetry_rows:
            with self._buffer_lock:
                self._buffer.extend(telemetry_rows)
                if len(self._buffer) >= BATCH_SIZE:
                    self._flush_buffer()

        # Ditto patch (non-blocking best-effort)
        if ditto_patch:
            thing_id = f"twinvoice:{asset_code}"
            try:
                self._ditto.merge_thing(thing_id, {"features": {"telemetry": {"properties": ditto_patch}}})
            except Exception:
                log.debug("ditto patch failed for %s", thing_id)

        # Valkey live fan-out
        if live_metrics:
            msg = json.dumps(
                {
                    "kind": "telemetry",
                    "payload": {"asset": asset_code, "t": now.isoformat(), "metrics": live_metrics},
                }
            )
            try:
                self._valkey.publish(f"live:{asset_code}", msg)
            except Exception:
                log.debug("valkey publish failed for %s", asset_code)

    def _handle_asset_metrics(self, asset_id: uuid.UUID, metrics: dict[str, Any], now: datetime) -> None:
        """Turn one asset's payload into a state transition, a production row and an energy row."""
        state = metrics.get("state")
        if state is not None:
            self._handle_state_change(asset_id, str(state), now)

        previous = self._last_counters.setdefault(asset_id, {})

        good = _as_float(metrics.get("good_count"))
        reject = _as_float(metrics.get("reject_count"))
        if good is not None or reject is not None:
            good_delta = _counter_delta(previous, "good_count", good)
            reject_delta = _counter_delta(previous, "reject_count", reject)
            # A row per interval, not per cycle: analytics sums these, so zero-delta rows would
            # only add noise. Cycle time still rides along on the intervals that produced.
            if good_delta or reject_delta:
                self._production_buffer.append(
                    {
                        "time": now,
                        "asset_id": asset_id,
                        "good_count": good_delta,
                        "reject_count": reject_delta,
                        "cycle_time_s": _as_float(metrics.get("cycle_time_s")),
                    }
                )

        power_kw = _as_float(metrics.get("power_kw"))
        energy_kwh = _as_float(metrics.get("energy_kwh"))
        if power_kw is not None and energy_kwh is not None:
            energy_delta = _counter_delta(previous, "energy_kwh", energy_kwh)
            power_factor = _as_float(metrics.get("power_factor"))
            current_a = power_kw * 1000.0 / (SQRT_3 * LINE_VOLTAGE_V * power_factor) if power_factor else None
            self._energy_buffer.append(
                {
                    "time": now,
                    "asset_id": asset_id,
                    "power_kw": power_kw,
                    "energy_kwh": energy_delta,
                    "power_factor": power_factor,
                    "current_a": current_a,
                    "voltage_v": LINE_VOLTAGE_V,
                    "tariff_rate": _tariff_rate(self._tariffs.get(asset_id), now),
                }
            )

    def _handle_state_change(self, asset_id: uuid.UUID, state: str, time_: datetime) -> None:
        """Write an event only when the state actually changes — the table stores transitions."""
        if state not in VALID_STATES or self._last_state.get(asset_id) == state:
            return
        self._last_state[asset_id] = state
        with self._session_factory() as session:
            event = AssetStateEvent(time=time_, asset_id=asset_id, state=state, source="simulator")
            session.add(event)
            session.commit()

    def _raise_alarm(self, alarm_data: dict[str, Any]) -> None:
        with self._session_factory() as session:
            from app.modules.telemetry.repository import AlarmRepository

            repo = AlarmRepository(session)

            # Dedupe: one active alarm per (rule, asset)
            existing = repo.active_for_rule_and_asset(alarm_data["rule_id"], alarm_data["asset_id"])
            if existing is not None:
                return

            alarm = Alarm(**alarm_data)
            repo.create(alarm)
            session.commit()

            # Publish alarm to Valkey for live fan-out
            msg = json.dumps(
                {
                    "kind": "alarm",
                    "payload": {
                        "id": str(alarm.id),
                        "asset_id": str(alarm.asset_id),
                        "severity": alarm.severity,
                        "title": alarm.title,
                        "message": alarm.message,
                        "status": alarm.status,
                    },
                }
            )
            with contextlib.suppress(Exception):
                self._valkey.publish("alarms", msg)

    def _flush_buffer(self) -> None:
        with self._buffer_lock:
            rows = self._buffer[:]
            energy_rows = self._energy_buffer[:]
            production_rows = self._production_buffer[:]
            self._buffer.clear()
            self._energy_buffer.clear()
            self._production_buffer.clear()

        if not rows and not energy_rows and not production_rows:
            return

        self._insert(
            rows,
            "INSERT INTO telemetry (time, sensor_id, value, quality) VALUES (:time, :sensor_id, :value, :quality)",
            "telemetry",
        )
        self._insert(
            energy_rows,
            "INSERT INTO energy_readings "
            "(time, asset_id, power_kw, energy_kwh, power_factor, current_a, voltage_v, tariff_rate) "
            "VALUES (:time, :asset_id, :power_kw, :energy_kwh, :power_factor, :current_a, "
            ":voltage_v, :tariff_rate)",
            "energy",
        )
        self._insert(
            production_rows,
            "INSERT INTO production_counts "
            "(time, asset_id, good_count, reject_count, cycle_time_s) "
            "VALUES (:time, :asset_id, :good_count, :reject_count, :cycle_time_s)",
            "production",
        )
        self._last_flush = time.monotonic()

    def _insert(self, rows: list[dict[str, Any]], sql: str, label: str) -> None:
        if not rows:
            return
        try:
            with self._session_factory() as session:
                session.execute(text(sql), rows)
                session.commit()
        except Exception:
            log.exception("failed to flush %d %s rows", len(rows), label)

    def _flush_loop(self) -> None:
        while self._running:
            time.sleep(FLUSH_INTERVAL_S)
            elapsed = time.monotonic() - self._last_flush
            if elapsed >= FLUSH_INTERVAL_S:
                self._flush_buffer()

    def _refresh_caches(self) -> None:
        try:
            with self._session_factory() as session:
                self._metric_map = _build_metric_map(session)
                self._asset_map = _build_asset_map(session)
                self._tariffs = _load_tariffs(session)
                self._alarm_rules = _load_alarm_rules(session)
                if not self._last_state:
                    self._last_state = _load_last_states(session)
            log.info(
                "caches refreshed: %d metrics, %d assets, %d rules",
                len(self._metric_map),
                len(self._asset_map),
                sum(len(v) for v in self._alarm_rules.values()),
            )
        except Exception:
            log.exception("cache refresh failed")

    def _refresh_loop(self) -> None:
        while self._running:
            time.sleep(60)
            self._refresh_caches()
