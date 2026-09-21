"""MQTT output: Sparkplug B edge nodes (one client per line), commands/acks and waveform bursts."""

from __future__ import annotations

import base64
import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from twinvoice_contracts.sparkplug import (
    REBIRTH_METRIC,
    MessageType,
    MetricDict,
    build_topic,
    dbirth,
    ddata,
    ddeath,
    decode_payload,
    nbirth,
    ndeath,
    now_ms,
)

from sim.commands import COMMAND_TOPIC_FILTER, ack_topic, handle_command
from sim.engine import iso
from sim.live import AssetSnapshot, LiveRuntime
from sim.machines.base import Waveform
from sim.physics.bearing_waveform import SAMPLE_RATE_HZ
from sim.sensors import MetricDef

log = logging.getLogger(__name__)

GOOD_QUALITY = 192
BAD_QUALITY = 0
KEEPALIVE_S = 30
RECONNECT_MIN_S = 1
RECONNECT_MAX_S = 30

type Values = dict[str, float | int | str | None]


def build_metrics(
    defs: list[MetricDef], values: Values, jitter_ms: dict[str, int], ts: int, birth: bool
) -> list[MetricDict]:
    metrics = []
    for d in defs:
        value = values.get(d.name)
        metric = MetricDict(
            name=d.name, datatype=d.datatype, value=value, timestamp=ts + jitter_ms.get(d.name, 0)
        )
        properties: dict[str, str | int] = {}
        if birth and d.unit:
            properties["engUnit"] = d.unit
        if value is None:
            properties["Quality"] = BAD_QUALITY
        elif birth:
            properties["Quality"] = GOOD_QUALITY
        if properties:
            metric["properties"] = properties
        metrics.append(metric)
    return metrics


def _client(client_id: str, host: str, port: int) -> mqtt.Client:
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=client_id)
    client.reconnect_delay_set(RECONNECT_MIN_S, RECONNECT_MAX_S)
    client.on_connect_fail = lambda _client, _userdata: log.warning(
        "%s: MQTT broker %s:%s unreachable, retrying", client_id, host, port
    )
    return client


class SparkplugEdgeNode:
    """One Sparkplug B edge node with its own MQTT session, NDEATH will and devices."""

    def __init__(self, host: str, port: int, group_id: str, edge_node_id: str) -> None:
        self.host, self.port = host, port
        self.group_id, self.edge_node_id = group_id, edge_node_id
        self._defs: dict[str, list[MetricDef]] = {}
        self._last: dict[str, tuple[Values, dict[str, int]]] = {}
        self._born: set[str] = set()
        self._bd_seq = 0
        self._seq = 0
        self._lock = threading.RLock()
        self._client = _client(f"twinvoice-{group_id}-{edge_node_id}", host, port)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._set_will()

    def _topic(self, message_type: MessageType, device: str | None = None) -> str:
        return build_topic(self.group_id, message_type, self.edge_node_id, device)

    def _set_will(self) -> None:
        self._client.will_set(self._topic(MessageType.NDEATH), ndeath(self._bd_seq), qos=1)

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) % 256
        return self._seq

    @property
    def connected(self) -> bool:
        return self._client.is_connected()

    @property
    def devices(self) -> set[str]:
        return set(self._defs)

    def add_device(self, device: str, defs: list[MetricDef]) -> None:
        self._defs[device] = defs

    def start(self) -> None:
        self._client.connect_async(self.host, self.port, keepalive=KEEPALIVE_S)
        self._client.loop_start()

    def stop(self) -> None:
        if self.connected:
            with self._lock:
                for device in sorted(self._born):
                    topic = self._topic(MessageType.DDEATH, device)
                    self._client.publish(topic, ddeath(self._next_seq()), qos=0)
                self._client.publish(self._topic(MessageType.NDEATH), ndeath(self._bd_seq), qos=1)
                self._born.clear()
            self._client.disconnect()
        self._client.loop_stop()

    def publish_device(self, device: str, values: Values, jitter_ms: dict[str, int]) -> None:
        self._last[device] = (values, jitter_ms)
        if not self.connected:
            return
        with self._lock:
            if device not in self._born:
                self._publish_dbirth(device)
                return
            metrics = build_metrics(self._defs[device], values, jitter_ms, now_ms(), birth=False)
            payload = ddata(metrics, self._next_seq())
            self._client.publish(self._topic(MessageType.DDATA, device), payload, qos=0)

    def rebirth(self) -> None:
        with self._lock:
            self._seq = 0
            self._client.publish(self._topic(MessageType.NBIRTH), nbirth(self._bd_seq), qos=0)
            self._born.clear()
            for device in self._last:
                self._publish_dbirth(device)

    def _publish_dbirth(self, device: str) -> None:
        values, jitter = self._last[device]
        metrics = build_metrics(self._defs[device], values, jitter, now_ms(), birth=True)
        topic = self._topic(MessageType.DBIRTH, device)
        self._client.publish(topic, dbirth(metrics, self._next_seq()), qos=0)
        self._born.add(device)

    def _on_connect(
        self, client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _props: Any
    ) -> None:
        if reason_code.is_failure:
            log.warning("edge node %s: connect refused: %s", self.edge_node_id, reason_code)
            return
        log.info("edge node %s connected to %s:%s", self.edge_node_id, self.host, self.port)
        client.subscribe(self._topic(MessageType.NCMD), qos=1)
        self.rebirth()

    def _on_disconnect(
        self, _client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _props: Any
    ) -> None:
        level = logging.WARNING if reason_code.is_failure else logging.INFO
        log.log(level, "edge node %s disconnected: %s", self.edge_node_id, reason_code)
        with self._lock:
            self._born.clear()
            # A new session needs a new bdSeq, and the will must carry it before reconnecting.
            self._bd_seq = (self._bd_seq + 1) % 256
            self._set_will()

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            metrics = decode_payload(message.payload)["metrics"]
        except Exception:
            log.warning("edge node %s: undecodable NCMD", self.edge_node_id)
            return
        if any(m["name"] == REBIRTH_METRIC and m.get("value") is True for m in metrics):
            log.info("edge node %s: rebirth requested", self.edge_node_id)
            self.rebirth()


class CommandChannel:
    """Plain MQTT client for twin write-back commands, their acks and waveform bursts."""

    def __init__(self, host: str, port: int, handler: Callable[[str, str, bytes], dict[str, Any]]):
        self.host, self.port = host, port
        self._handler = handler
        self._client = _client("twinvoice-simulator-control", host, port)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def start(self) -> None:
        self._client.connect_async(self.host, self.port, keepalive=KEEPALIVE_S)
        self._client.loop_start()

    def stop(self) -> None:
        if self._client.is_connected():
            self._client.disconnect()
        self._client.loop_stop()

    @property
    def connected(self) -> bool:
        return self._client.is_connected()

    def publish_json(self, topic: str, body: dict[str, Any], qos: int = 0) -> None:
        if self.connected:
            self._client.publish(topic, json.dumps(body, separators=(",", ":")), qos=qos)

    def _on_connect(
        self, client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _props: Any
    ) -> None:
        if not reason_code.is_failure:
            client.subscribe(COMMAND_TOPIC_FILTER, qos=1)

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        parts = message.topic.split("/")
        if len(parts) != 4:
            return
        asset_code, command = parts[2], parts[3]
        ack = self._handler(asset_code, command, message.payload)
        self.publish_json(ack_topic(asset_code), ack, qos=1)


def waveform_message(asset_code: str, wave: Waveform) -> dict[str, Any]:
    samples = wave.samples.astype("<f4")
    return {
        "asset_code": asset_code,
        "component_code": wave.component_code,
        "metric_name": f"{wave.component_code}.vib_wave",
        "t": iso(datetime.now(UTC)),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "n_samples": int(samples.size),
        "samples_b64": base64.b64encode(samples.tobytes()).decode("ascii"),
        "defect_freqs_hz": wave.defect_freqs_hz,
    }


class MqttBridge:
    """Live fleet over MQTT: Sparkplug DDATA per asset, commands, acks and waveforms."""

    def __init__(self, host: str, port: int, runtime: LiveRuntime) -> None:
        plant = runtime.catalog.fleet.plant.code
        self.nodes = {
            line.code: SparkplugEdgeNode(host, port, plant, line.code)
            for line in runtime.catalog.fleet.lines
        }
        for line in runtime.catalog.fleet.lines:
            for asset in line.assets:
                self.nodes[line.code].add_device(asset.code, runtime.metric_defs[asset.code])
        self.commands = CommandChannel(
            host,
            port,
            lambda asset, command, payload: handle_command(runtime, asset, command, payload),
        )
        runtime.engine_replaced.append(self.rebirth)

    def start(self) -> None:
        for node in self.nodes.values():
            node.start()
        self.commands.start()

    def stop(self) -> None:
        for node in self.nodes.values():
            node.stop()
        self.commands.stop()

    @property
    def connected(self) -> bool:
        return self.commands.connected

    def rebirth(self) -> None:
        for node in self.nodes.values():
            if node.connected:
                node.rebirth()

    async def publish(self, snapshots: list[AssetSnapshot]) -> None:
        for snap in snapshots:
            self.nodes[snap.line_code].publish_device(snap.code, snap.values, snap.jitter_ms)

    def publish_waveforms(self, waves: list[tuple[str, Waveform]]) -> None:
        for asset_code, wave in waves:
            self.commands.publish_json(
                f"twinvoice/wave/{asset_code}", waveform_message(asset_code, wave)
            )
